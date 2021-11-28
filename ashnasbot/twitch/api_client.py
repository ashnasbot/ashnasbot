import logging
import urllib.parse

import aiohttp
from oauthlib.oauth2 import BackendApplicationClient
from requests_oauthlib import OAuth2Session

from . import db
from .. import config

API_BASE = "https://api.twitch.tv"
logger = logging.getLogger(__name__)

token = None


class TwitchClient():

    # Use the same session for matching clients, no matter the instance.
    __sessions = {}

    def __init__(self, client_id=None, target_user=None):
        global token
        cfg = config.Config()
        self.client_id = cfg["client_id"]
        logger.debug(f"Creating twitch API client for {self.client_id} {target_user}")

        self.target_user = target_user
        self.channel_id = None
        self.global_badges = {}

        if not token:
            logger.warning("No token - retriving new token")
            body = urllib.parse.urlencode({'client_id': self.client_id, 'client_secret': cfg["secret"]})
            client = BackendApplicationClient(client_id=cfg["client_id"])
            oauth = OAuth2Session(client=client)
            try:
                token = oauth.fetch_token(token_url='https://id.twitch.tv/oauth2/token', body=body)
            except Exception:
                raise ValueError("OAuth: failed to get token")

        self.oauth = token["access_token"]

    async def _make_api_request(self, url, params=None):
        headers = {
            "Client-ID": f"{self.client_id}",
            "Accept": "application/vnd.twitchtv.v5+json",
        }

        if "helix" in url:
            headers["Authorization"] = f"Bearer {self.oauth}"

        session = self.__sessions.get(self.client_id, None)

        if not session or session.closed:
            logger.info("Starting new client API session")
            session = aiohttp.ClientSession(raise_for_status=True)
            self.__sessions[self.client_id] = session

        if not url.startswith("http"):
            url = API_BASE + url

        async with session.get(url, params=params, headers=headers) as resp:
            # TODO: check status (too many requests? etc)
            return await resp.json()

    async def get_channel_id(self, channel=None):
        url = "/helix/users"
        own_id = False
        if not channel:
            own_id = True
            channel = self.target_user

        params = {'login': channel}

        logger.debug("Getting id for channel (%s)", channel)

        resp = await self._make_api_request(url, params)
        if "data" not in resp or len(resp["data"]) < 1:
            raise ValueError(f"Channel {self.target_user} does not exist.")
        channel_id = resp["data"][0]["id"]
        if own_id:
            self.channel_id = channel_id
        return channel_id

    async def get_user_info(self, user):
        url = "/helix/users"
        if not user:
            return {}
        if user.isnumeric():
            params = {'id': user}
        else:
            params = {'login': user}

        logger.debug("Getting user info for %s", user)

        resp = await self._make_api_request(url, params=params)

        if "data" not in resp or len(resp["data"]) < 1:
            logger.warning("User %s not found", user)
            return {}
        return resp["data"][0]

    async def get_new_followers(self):
        emit = True
        if self.channel_id is None:
            await self.get_channel_id()
            emit = False

        url = "/helix/users/follows"

        recent_followers = await self._make_api_request(
            url,
            {
                'limit': 10,
                'to_id': self.channel_id
            })
        new_follows = []

        tbl_name = self.target_user + "_follows"

        if not db.exists(tbl_name):
            db.create(tbl_name, primary="name")
            emit = False

        tbl = db.get(tbl_name)
        existing_follows = [e["id"] for e in tbl]

        for user in recent_followers['data']:
            if int(user["from_id"]) not in existing_follows:
                new_follows.append({"username": user['from_name'], "id": user["from_id"]})
                if emit:
                    logger.info("FOLLOW %s is a new follower", user['from_name'], )

        if new_follows:
            db.update_multi(tbl_name, new_follows, primary="username", keys=["username"])

        if emit:
            return [u["username"] for u in new_follows]
        else:
            return []

    async def get_badges_for_channel(self, channel):
        logger.debug("Getting badges for %s", channel)
        channel_id = await self.get_channel_id(channel)
        if not channel_id:
            return {}

        logger.debug("Getting badges for %s", channel_id)
        url = "/helix/chat/badges"

        resp = await self._make_api_request(url, {"broadcaster_id": channel_id})

        badges = {}

        for badge in resp["data"]:
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

        for badge in resp["data"]:
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

        try:
            for cheer in resp["data"]:
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
