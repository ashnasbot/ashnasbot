import asyncio
import logging
import time
import urllib.parse

import aiohttp
from oauthlib.oauth2 import BackendApplicationClient
from requests_oauthlib import OAuth2Session

from . import db
from .. import config

API_BASE = "https://api.twitch.tv"
TOKEN_CACHE = {}
USER_TOKENS = {}
logger = logging.getLogger(__name__)

_AUTH_SESSION: aiohttp.ClientSession | None = None


def _auth_session() -> aiohttp.ClientSession:
    """Shared session for id.twitch.tv auth calls (no raise_for_status —
    auth endpoints signal expiry via status codes we want to inspect)."""
    global _AUTH_SESSION
    if not _AUTH_SESSION or _AUTH_SESSION.closed:
        _AUTH_SESSION = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))
    return _AUTH_SESSION


class ManagedToken:
    """An OAuth access token that validates and auto-refreshes against Twitch.

    Reads and writes directly to the Config singleton so refreshed tokens are
    persisted without any external coordination.
    """

    def __init__(self, token_key: str, refresh_key: str):
        self._token_key = token_key
        self._refresh_key = refresh_key
        self._valid: bool | None = None
        self._expires_at: float = 0.0

    async def get(self) -> str | None:
        """Return a valid token, refreshing automatically if needed.

        Returns None if no token is configured or if refresh fails.
        """
        cfg = config.Config()
        token = cfg.get(self._token_key, None)
        if not token:
            return None
        if self._valid and time.time() >= self._expires_at - 300:
            logger.info("Token '%s' nearing expiry — refreshing proactively", self._token_key)
            self._valid = None
        if self._valid is None:
            expires_in = await TwitchClient.validate_token(token)
            if expires_in is None:
                # Network error — can't tell if the token is bad; don't burn a
                # refresh-token rotation on it. Use the token and re-check later.
                logger.warning("Token '%s' validation unavailable — assuming still valid", self._token_key)
                return token
            if expires_in:
                self._valid = True
                self._expires_at = time.time() + expires_in
            else:
                logger.warning("Token '%s' expired — attempting refresh", self._token_key)
                if await self._refresh():
                    token = cfg.get(self._token_key)
                    self._valid = True
                    self._expires_at = time.time() + 14400
                else:
                    logger.warning("Token '%s' refresh failed", self._token_key)
                    self._valid = False
        return token if self._valid else None

    async def _refresh(self) -> bool:
        cfg = config.Config()
        refresh_token = cfg.get(self._refresh_key, None)
        if not refresh_token:
            logger.warning("No refresh token stored for '%s'", self._refresh_key)
            return False
        client_id = cfg.get("client_id", None)
        client_secret = cfg.get("secret", None)
        new_token = await TwitchClient.refresh_bot_token(refresh_token, client_id, client_secret)
        if not new_token:
            return False
        cfg.update(self._token_key, new_token["access_token"])
        if new_token.get("refresh_token"):
            cfg.update(self._refresh_key, new_token["refresh_token"])
        logger.info("Token '%s' refreshed successfully", self._token_key)
        return True

    def invalidate(self):
        """Force re-validation on next get(), e.g. after a config reload."""
        self._valid = None
        self._expires_at = 0.0


class ChannelToken:
    """Per-channel broadcaster OAuth token, backed by the channel_tokens db table.

    Each instance manages one row keyed by channel name: validates on first use,
    caches the result, and refreshes automatically when the token expires.
    """

    TABLE = "channel_tokens"

    def __init__(self, channel: str):
        self._channel = channel
        self._valid: bool | None = None
        self._expires_at: float = 0.0
        db.ensure(self.TABLE, "channel")

    async def get(self) -> str | None:
        """Return a valid token, refreshing automatically if needed.

        Returns None if no token is stored for this channel, if the stored
        token belongs to a different channel, or if refresh fails.
        """
        row = db.find(self.TABLE, channel=self._channel)
        if not row:
            return None
        login_for = row.get("login_for")
        if login_for and login_for.lower() != self._channel.lower():
            logger.warning(
                "Channel token for '%s' belongs to '%s' — refusing to use it",
                self._channel, login_for)
            return None
        token = row["access_token"]
        if self._valid and time.time() >= self._expires_at - 300:
            logger.info("Channel token for '%s' nearing expiry — refreshing", self._channel)
            self._valid = None
        if self._valid is None:
            expires_in = await TwitchClient.validate_token(token)
            if expires_in is None:
                logger.warning("Channel token validation for '%s' unavailable — assuming still valid",
                               self._channel)
                return token
            if expires_in:
                self._valid = True
                self._expires_at = time.time() + expires_in
            else:
                logger.warning("Channel token for '%s' expired — attempting refresh", self._channel)
                if await self._refresh():
                    row = db.find(self.TABLE, channel=self._channel)
                    token = row["access_token"]
                    self._valid = True
                    self._expires_at = time.time() + 14400
                else:
                    logger.warning("Channel token refresh failed for '%s'", self._channel)
                    self._valid = False
        return token if self._valid else None

    async def _refresh(self) -> bool:
        row = db.find(self.TABLE, channel=self._channel)
        if not row or not row.get("refresh_token"):
            return False
        cfg = config.Config()
        new_token = await TwitchClient.refresh_bot_token(
            row["refresh_token"], cfg.get("client_id"), cfg.get("secret"))
        if not new_token:
            return False
        db.update(self.TABLE, {
            "channel": self._channel,
            "access_token": new_token["access_token"],
            "refresh_token": new_token.get("refresh_token", row["refresh_token"]),
        }, ["channel"])
        logger.info("Channel token for '%s' refreshed successfully", self._channel)
        return True

    def invalidate(self):
        """Force re-validation on next get(), e.g. after a config reload."""
        self._valid = None
        self._expires_at = 0.0


class TwitchClient():

    # Use the same session for matching clients, no matter the instance.
    __sessions = {}

    def __init__(self, client_id=None, target_user=None):
        cfg = config.Config()
        if client_id:
            self.client_id = client_id
        else:
            self.client_id = cfg["client_id"]
        logger.debug(f"Creating twitch API client for {self.client_id} {target_user}")

        self.target_user = target_user
        self.channel_id = None
        self.global_badges = {}
        self.oauth = None

    def get_app_token(self):
        if self.oauth is None:
            if self.client_id in TOKEN_CACHE:
                logger.debug("Using cached API auth token")
                token = TOKEN_CACHE[self.client_id]
            else:
                cfg = config.Config()
                logger.info("Retrieving API auth token")
                body = urllib.parse.urlencode({
                    'client_id': self.client_id,
                    'client_secret': cfg["secret"]
                })
                client = BackendApplicationClient(client_id=cfg["client_id"])
                oauth = OAuth2Session(client=client)
                try:
                    token = oauth.fetch_token(token_url='https://id.twitch.tv/oauth2/token', body=body)
                    TOKEN_CACHE[self.client_id] = token
                except Exception:
                    self.oauth = ''
                    raise ValueError("OAuth: failed to get token")

            self.oauth = token["access_token"]

    @classmethod
    def set_user_token(cls, token):
        cfg = config.Config()
        client_id = cfg["client_id"]
        USER_TOKENS[client_id] = token

    @staticmethod
    async def validate_token(token):
        """Return expires_in (int > 0) if valid, False if expired/rejected, None on network error."""
        try:
            async with _auth_session().get(
                "https://id.twitch.tv/oauth2/validate",
                headers={"Authorization": f"OAuth {token}"}
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("expires_in", 1)
                return False
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logger.warning("Token validation request failed: %s", e)
            return None

    @staticmethod
    async def refresh_bot_token(refresh_token, client_id, client_secret):
        """Exchange a refresh token for a new access token.

        Returns the token response dict on success (contains 'access_token' and
        usually a new 'refresh_token'), or None on failure.
        """
        try:
            async with _auth_session().post(
                "https://id.twitch.tv/oauth2/token",
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": client_id,
                    "client_secret": client_secret,
                }
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
                body = await resp.text()
                logger.warning("Bot token refresh failed: HTTP %s — %s", resp.status, body)
                return None
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logger.warning("Bot token refresh request failed: %s", e)
            return None

    @classmethod
    def _get_session(cls, client_id):
        """Return the shared aiohttp session for this client_id, creating it if needed."""
        session = cls.__sessions.get(client_id)
        if not session or session.closed:
            logger.info("Starting new client API session")
            session = aiohttp.ClientSession(
                raise_for_status=True, timeout=aiohttp.ClientTimeout(total=30))
            cls.__sessions[client_id] = session
        return session

    async def close(self):
        """Close all shared API sessions.

        Sessions are pooled per client_id across all TwitchClient instances,
        so this should only be called at application shutdown.
        """
        logger.info("Closing client API sessions")
        while self.__sessions:
            c, s = self.__sessions.popitem()
            logger.debug("Cleaning up client session for client %s", c)
            await s.close()
        if _AUTH_SESSION and not _AUTH_SESSION.closed:
            await _AUTH_SESSION.close()

    async def _make_api_request(self, url, params=None, postdata=None, _retry=True):
        """Make a Twitch API request. Returns the parsed JSON body, or None on failure."""
        headers = {
            "Client-ID": f"{self.client_id}",
            "Accept": "application/vnd.twitchtv.v5+json",
        }

        if "helix" in url:
            if not self.oauth:
                await asyncio.to_thread(self.get_app_token)
            headers["Authorization"] = f"Bearer {self.oauth}"

        session = self._get_session(self.client_id)

        if not url.startswith("http"):
            url = API_BASE + url

        try:
            if postdata:
                async with session.post(url, params=params, headers=headers, json=postdata) as resp:
                    return await resp.json()
            else:
                async with session.get(url, params=params, headers=headers) as resp:
                    return await resp.json()
        except aiohttp.ClientResponseError as e:
            if e.status == 401 and _retry:
                # App token expired mid-flight — drop the cache and retry once.
                logger.warning("API request unauthorized — refetching app token")
                TOKEN_CACHE.pop(self.client_id, None)
                self.oauth = None
                return await self._make_api_request(url, params, postdata, _retry=False)
            if e.status == 429:
                logger.warning("Twitch API rate limit hit: %s", url)
            else:
                logger.error("Twitch API request failed (HTTP %s): %s", e.status, url)
            return None
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logger.error("Twitch API request error for %s: %s", url, e)
            return None

    async def get_channel_id(self, channel=None):
        url = "/helix/users"
        own_id = False
        if not channel:
            own_id = True
            channel = self.target_user

        params = {'login': channel}

        logger.debug("Getting id for channel (%s)", channel)

        resp = await self._make_api_request(url, params)
        if not resp or not resp.get("data"):
            raise ValueError(f"Channel {channel} does not exist.")
        channel_id = resp["data"][0]["id"]
        if own_id:
            self.channel_id = channel_id
        return channel_id

    async def get_channel_info(self, channel_id: str) -> dict:
        resp = await self._make_api_request("/helix/channels", {"broadcaster_id": channel_id})
        if resp and resp.get("data"):
            return resp["data"][0]
        return {}

    async def get_user_info(self, user):
        url = "/helix/users"
        if not user:
            return {}
        if isinstance(user, int):
            params = {'id': user}
        elif user.isnumeric():
            params = {'id': int(user)}
        else:
            params = {'login': user}

        logger.debug("Getting user info for %s", user)

        resp = await self._make_api_request(url, params=params)

        if not resp or not resp.get("data"):
            logger.warning("User %s not found", user)
            return {}
        return resp["data"][0]

    async def get_badges_for_channel(self, channel):
        logger.debug("Getting badges for %s", channel)
        channel_id = await self.get_channel_id(channel)
        if not channel_id:
            return {}

        logger.debug("Getting badges for %s", channel_id)
        url = "/helix/chat/badges"

        resp = await self._make_api_request(url, {"broadcaster_id": channel_id})

        badges = {}
        if not resp:
            return badges

        for badge in resp.get("data", []):
            name = badge["set_id"]
            if len(badge["versions"]) > 1:
                for ver in badge["versions"]:
                    fullname = name + str(ver["id"])
                    badges[fullname] = ver["image_url_2x"]
            else:
                badges[badge["set_id"]] = badge["versions"][0]["image_url_2x"]

        return badges

    async def get_global_badges(self):
        logger.debug("Getting global badges")
        if self.global_badges:
            return self.global_badges

        url = "/helix/chat/badges/global"
        resp = await self._make_api_request(url)

        badges = {}
        if not resp:
            return badges

        for badge in resp.get("data", []):
            name = badge["set_id"]
            if len(badge["versions"]) > 1:
                for ver in badge["versions"]:
                    fullname = name + str(ver["id"])
                    badges[fullname] = ver["image_url_2x"]
            else:
                badges[badge["set_id"]] = badge["versions"][0]["image_url_2x"]

        # Set the cache
        self.global_badges = badges
        return badges

    async def get_cheermotes(self, channel=None):
        url = "/helix/bits/cheermotes"
        params = {}
        if channel:
            params["broadcaster_id"] = await self.get_channel_id(channel)
            logger.debug("Getting channel cheermotes for %s", channel)
        else:
            logger.debug("Getting global cheermotes")

        cheermotes = {}
        resp = await self._make_api_request(url, params)
        if not resp:
            return cheermotes

        try:
            for cheer in resp.get("data", []):
                prefix = cheer["prefix"]
                tiers = {}
                for teir in cheer["tiers"]:
                    img = teir["images"]["dark"]["animated"]["2"]
                    value = teir["id"]
                    tiers[value] = img
                cheermotes[prefix] = tiers
        except Exception:
            logger.warning("Failed to get cheermotes")

        return cheermotes

    async def get_clip(self, clip):
        url = "https://api.twitch.tv/helix/clips"
        params = {'id': clip}
        logger.debug("Getting clip details for slug: %s", clip)
        return await self._make_api_request(url, params=params)

    async def get_emotes_for_sets(self, sets):
        url = '/helix/chat/emotes/set'

        params = [('emote_set_id', s) for s in sets]
        encoded_params = urllib.parse.urlencode(params)
        emotes = {}
        logger.debug("Getting channel emote sets for %s", sets)

        resp = await self._make_api_request(url, encoded_params)
        if not resp:
            logger.warning("Failed to get emote sets")
            return emotes

        try:
            for emote in resp.get("data", []):
                name = emote["name"]
                info = {
                    "id": emote["id"],
                    "format": emote["format"][-1],
                    "theme_mode": "dark",
                    "scale": "2.0"
                }
                emotes[name] = (resp["template"].format().format(**info), emote["emote_set_id"])
        except (KeyError, IndexError):
            logger.exception("Failed to parse emote sets")

        return emotes

    async def create_prediction(self, birds):
        CHOCOBOS = dict(zip([1, 2, 3, 4, 5, 6], birds))
        # CHOCOBOS = {
        #    1: "1 (Green)",
        #    2: "2 (Blue)",
        #    3: "3 (Pink)",
        #    4: "4 (Red)",
        #    5: "5 (Purple)",
        #    6: "6 (White)"
        # }
        url = '/helix/predictions'
        broadcaster_id = self.channel_id
        if broadcaster_id is None:
            broadcaster_id = await self.get_channel_id(self.target_user or 'ashnas')

        cfg = config.Config()
        client_id = cfg["client_id"]
        user_token = USER_TOKENS.get(client_id)
        if not user_token:
            logger.error("No user token for predictions — start a race with auth first")
            return None
        self.oauth = user_token['access_token']

        data = {
            "broadcaster_id": broadcaster_id,
            "title": "Which Chocobo will win the Race?",
            "outcomes": [
                {"title": chocobo} for chocobo in CHOCOBOS.values()
            ],
            "prediction_window": 80}

        logger.debug("Creating prediction: %s", data)

        resp = await self._make_api_request(url, postdata=data)
        if not resp or not resp.get("data"):
            logger.error("Failed to create prediction: %s", resp)
            return None

        respdata = resp["data"][0]
        ret = {}
        ret["broadcaster_id"] = respdata["broadcaster_id"]
        ret["prediction_id"] = respdata["id"]
        ret["birbs"] = {}

        for outcome in respdata["outcomes"]:
            idx = list(CHOCOBOS.values()).index(outcome["title"])
            ret["birbs"][list(CHOCOBOS.keys())[idx]] = outcome["id"]

        return ret

    async def resolve_prediction(self, pid, data, result):
        url = "https://api.twitch.tv/helix/predictions"
        headers = {
            "Client-ID": f"{self.client_id}",
            "Accept": "application/vnd.twitchtv.v5+json",
        }

        cfg = config.Config()
        client_id = cfg["client_id"]
        user_token = USER_TOKENS.get(client_id)
        if not user_token:
            logger.error("No user token to resolve prediction")
            return None
        self.oauth = user_token['access_token']

        headers["Authorization"] = f"Bearer {self.oauth}"

        session = self._get_session(self.client_id)

        params = {
            "broadcaster_id": data["broadcaster_id"],
            "id": pid,
            "status": "RESOLVED",
            "winning_outcome_id": data["birbs"][result]
        }

        try:
            async with session.patch(url, params=params, headers=headers) as resp:
                return await resp.json()
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logger.error("Failed to resolve prediction: %s", e)
            return None

    async def get_user_emotes(self, user_id, user_token):
        url = "https://api.twitch.tv/helix/chat/emotes/user"
        headers = {
            "Client-ID": f"{self.client_id}",
            "Authorization": f"Bearer {user_token}",
        }
        session = self._get_session(self.client_id)
        emotes = {}
        try:
            async with session.get(url, params={"user_id": user_id}, headers=headers) as resp:
                data = await resp.json()
            template = data.get("template", "")
            for emote in data.get("data", []):
                name = emote["name"]
                info = {
                    "id": emote["id"],
                    "format": emote["format"][-1],
                    "theme_mode": "dark",
                    "scale": "2.0",
                }
                emotes[name] = (template.format().format(**info), emote["emote_set_id"])
        except Exception as e:
            logger.warning("Failed to get user emotes: %s", e)
        return emotes

    async def send_chat_message(self, broadcaster_id, sender_id, message, user_token, reply_to=None):
        url = "https://api.twitch.tv/helix/chat/messages"
        headers = {
            "Client-ID": f"{self.client_id}",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {user_token}",
        }
        data = {
            "broadcaster_id": broadcaster_id,
            "sender_id": sender_id,
            "message": message,
        }
        if reply_to:
            data["reply_parent_message_id"] = reply_to

        session = self._get_session(self.client_id)
        try:
            async with session.post(url, headers=headers, json=data) as resp:
                body = await resp.json()
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logger.error("Failed to send chat message: %s", e)
            return None

        # A 200 response can still mean the message was dropped (e.g. AutoMod)
        sent = body.get("data", [{}])[0] if isinstance(body, dict) else {}
        if sent and not sent.get("is_sent", True):
            reason = sent.get("drop_reason", {})
            logger.warning("Chat message dropped: %s", reason.get("message", reason))
        return body

    async def subscribe_eventsub(self, session_id, subscription_type, condition, channel_id, user_token):

        url = "https://api.twitch.tv/helix/eventsub/subscriptions"
        headers = {
            "Client-ID": f"{self.client_id}",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {user_token}"
        }

        session = self._get_session(self.client_id)

        postdata = {
            "type": subscription_type[0],
            "version": subscription_type[1],
            "condition": condition,
            "transport": {
                "method": "websocket",
                "session_id": session_id,
            }
        }
        logger.debug(postdata)

        try:
            async with session.post(url, headers=headers, json=postdata, raise_for_status=False) as resp:
                body = await resp.json(content_type=None)
                if resp.status in (200, 202):
                    return body
                if resp.status == 409:
                    logger.debug("EventSub subscription already exists: %s", subscription_type[0])
                elif resp.status == 403:
                    msg = body.get("message", str(body)) if isinstance(body, dict) else str(body)
                    logger.warning(
                        "EventSub subscribe forbidden (%s): %s", subscription_type[0], msg)
                else:
                    logger.error("EventSub subscribe failed (%s %s): %s",
                                 subscription_type[0], resp.status, body)
                return None
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logger.error("EventSub subscribe request failed (%s): %s", subscription_type[0], e)
            return None
