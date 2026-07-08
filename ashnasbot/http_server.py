import aiohttp
import asyncio
import bisect
import json
import logging
import mimetypes
import os
from pathlib import Path
import random
import re
from requests_oauthlib import OAuth2Session

import base64
from cryptography import fernet
from aiohttp import web
import urllib.parse
from aiohttp_session import setup, get_session, new_session
from aiohttp_session.cookie_storage import EncryptedCookieStorage
from prometheus_async import aio

from ashnasbot.twitch import db
from ashnasbot.twitch.api_client import TwitchClient
from commands._racing_queue import race_commands, Empty

logger = logging.getLogger(__name__)
logging.getLogger("aiohttp.access").setLevel(logging.DEBUG)

mimetypes.add_type('image/webp', '.webp')  # add webp support as an image type for serving

# OAuth Details
auth_base_url = 'https://id.twitch.tv/oauth2/authorize'
token_url = 'https://id.twitch.tv/oauth2/token'
redirect_uri = "http://localhost:8080/authorize"
bot_redirect_uri = "http://localhost:8080/bot_authorize"

os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"


def _replace_state(url, state):
    """Replace the state query parameter of an authorization URL."""
    parts = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qs(parts.query)
    query["state"] = [state]
    return parts._replace(query=urllib.parse.urlencode(query, doseq=True)).geturl()


LOG_FORMAT = "%s %r %a"


class HTTPServer(object):
    def __init__(self, reload_evt=None, address='0.0.0.0', port=8080, loop=None, shutdown_evt=None,
                 client_id=None, secret=None, events=None, replay=None):
        self.address = address
        self.port = port
        self.reload_evt = reload_evt
        self.shutdown_evt = shutdown_evt
        if loop is None:
            loop = asyncio.get_event_loop()
        self.loop = loop
        self.site = None
        self.client_id = client_id
        self.secret = secret
        self.events = events
        self.replay_queue = replay

    async def start(self):
        logger.info('Starting webserver')
        self.app = web.Application(logger=logger)
        fernet_key = fernet.Fernet.generate_key()
        secret_key = base64.urlsafe_b64decode(fernet_key)
        setup(self.app, EncryptedCookieStorage(secret_key))
        self.setup_routes()
        self.runner = web.AppRunner(self.app, access_log_format=LOG_FORMAT)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, self.address, self.port)
        await self.site.start()
        logger.info('Serving on %s:%d' % (self.address, self.port))

    async def stop(self):
        if self.runner:
            logger.info('Stopping webserver')
            await self.runner.cleanup()

    @staticmethod
    async def get_dashboard(request):
        return web.HTTPFound('/static/dashboard.html')

    @staticmethod
    async def get_chat(request):
        return web.HTTPFound('/static/base/chat.html')

    @staticmethod
    async def get_favicon(request):
        return web.FileResponse('public/favicon.ico')

    def setup_routes(self):
        # API
        self.app.router.add_get('/api/config', self.get_config)
        self.app.router.add_get('/api/bot_status', self.get_bot_status)
        self.app.router.add_get('/api/token/refresh', self.get_token_refresh)
        self.app.router.add_get('/api/views', self.get_views)
        self.app.router.add_get('/res/{view}/sound/{event}', self.get_sound)
        self.app.router.add_get('/res/{view}/image/{name}', self.get_image)
        self.app.router.add_get('/res/{view}/media/{name}', self.get_media)
        self.app.router.add_get('/views/{view}/{base}', self.get_base)
        self.app.router.add_post('/api/config', self.post_config)
        self.app.router.add_post('/api/set_bot_token', self.post_set_bot_token)
        self.app.router.add_post('/api/shutdown', self.post_shutdown)
        self.app.router.add_get('/command', self.get_command)
        self.app.router.add_post('/replay_event', self.post_replay)
        self.app.router.add_post('/prediction', self.post_prediction)

        # Static
        try:
            self.app.router.add_static('/static', path="public/")
        except Exception:
            logger.error("No Static dir")

        try:
            self.app.router.add_static('/views', path="views/")
        except Exception:
            logger.warning("No views installed")

        # This is very important
        self.app.router.add_get('/favicon.ico', self.get_favicon)

        # Shortcuts
        self.app.router.add_get('/', self.get_chat)
        self.app.router.add_get('/dashboard', self.get_dashboard)
        self.app.router.add_get('/events', self.get_recent_events)
        self.app.router.add_get('/chat', self.get_chat)
        self.app.router.add_get('/user_auth', self.begin_auth)
        self.app.router.add_get('/authorize', self.auth_callback)
        self.app.router.add_get('/bot_auth', self.begin_bot_auth)
        self.app.router.add_get('/bot_authorize', self.bot_auth_callback)

        # Metrics
        self.app.router.add_get("/metrics", aio.web.server_stats)

    # Config keys that must never be sent to the browser.
    SENSITIVE_CONFIG_KEYS = ("secret", "oauth", "bot_refresh_token")

    @staticmethod
    async def get_config(request):
        with open('config.json', 'r') as config:
            config = json.load(config)
        for key in HTTPServer.SENSITIVE_CONFIG_KEYS:
            config.pop(key, None)
        bot_token = config.pop("bot_token", None)
        config["bot_configured"] = bool(bot_token)
        from ashnasbot.twitch.db import exists, find
        channel = request.query.get("channel", "").lower()
        channel_token_for = None
        if exists("channel_tokens"):
            if channel:
                row = find("channel_tokens", channel=channel)
                if row:
                    channel_token_for = (row.get("login_for") or channel).lower()
            else:
                row = find("channel_tokens")
                if row:
                    channel_token_for = (row.get("login_for") or "").lower()
        config["channel_configured"] = channel_token_for == channel if channel else bool(channel_token_for)
        if channel_token_for:
            config["channel_token_for"] = channel_token_for
        return web.json_response(config)

    async def get_bot_status(self, request):
        """Validate the stored bot token against Twitch's token introspection endpoint."""
        with open('config.json', 'r') as f:
            config = json.load(f)
        bot_token = config.get("bot_token")
        if not bot_token:
            return web.json_response({"configured": False, "valid": False})
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(
                    "https://id.twitch.tv/oauth2/validate",
                    headers={"Authorization": f"OAuth {bot_token}"}
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return web.json_response({
                            "configured": True,
                            "valid": True,
                            "expires_in": data.get("expires_in", 0),
                            "login": data.get("login", ""),
                        })
                    return web.json_response({"configured": True, "valid": False})
        except Exception as e:
            logger.warning("Bot token validation request failed: %s", e)
            return web.json_response({"configured": True, "valid": None})

    async def get_token_refresh(self, request):
        """Use the server-side refresh token to get a fresh access token for the channel.

        Returns JSON {"access_token": "...", "expires_in": N} and sets the 'token'
        cookie so the browser can continue without a page redirect.
        Returns 400 if no channel given, 404 if no stored token, 502 if Twitch refresh fails.
        """
        channel = request.query.get("channel", "").strip().lower()
        if not channel:
            return web.json_response({"error": "channel required"}, status=400)

        from ashnasbot.twitch.api_client import ChannelToken
        ct = ChannelToken(channel)
        token = await ct.get()
        if not token:
            return web.json_response({"error": "no valid token for channel"}, status=404)

        resp = web.json_response({"access_token": token, "expires_in": 14400})
        resp.set_cookie("token", token, max_age=14400, secure=True)
        resp.set_cookie("user", channel, max_age=14400 * 24, secure=True)
        return resp

    @staticmethod
    async def get_views(request):
        resp = []
        for path in os.scandir("views"):
            if path.is_dir():
                files = [f for f in os.scandir(path.path) if f.is_file()]
                has_chat = any(f.name == "chat.html" for f in files)
                has_css = any(f.name.endswith(".css") for f in files)
                if has_chat or has_css:
                    resp.append(path.name)
        return web.json_response(resp)

    async def get_recent_events(self, request):
        resp = []
        for evt in self.events:
            try:
                resp.insert(0, evt.__dict__)
            except AttributeError:
                resp.insert(0, evt)

        return web.json_response(resp)

    AUDIO_FILETYPES = [".wav", ".mp3", ".mp4", ".ogg", ".flac"]

    async def get_sound(self, request):
        view = request.match_info['view']
        event = request.match_info['event']
        views_path = os.path.join('views', view)

        ammt = self._query_int(request, "value")

        return self.glob_var([views_path, "public/audio"], event,
                             self.AUDIO_FILETYPES, ammt)

    @staticmethod
    def _query_int(request, key, default=0):
        try:
            return int(request.query.get(key, default))
        except ValueError:
            logger.warning("Bad %s query value: %r", key, request.query.get(key))
            return default

    async def get_base(self, request):
        view = request.match_info['view']
        base = request.match_info['base']
        base_path = Path('public', "base", base)
        views_path = Path('views', view, base)

        if views_path.exists():
            return web.FileResponse(views_path)
        if base_path.exists():
            return web.FileResponse(base_path)

        return web.HTTPNotFound()

    IMAGE_FILETYPES = [".png"]

    async def get_image(self, request):
        view = request.match_info['view']
        name = request.match_info['name']

        views_path = os.path.join('views', view)
        views_match = list(Path(views_path).glob(name + ".*"))

        for match in views_match:
            if match.suffix in self.IMAGE_FILETYPES:
                return web.FileResponse(match)

        fallback_match = list(Path("public/images").glob(name + ".*"))
        for match in fallback_match:
            if match.suffix in self.IMAGE_FILETYPES:
                return web.FileResponse(match)

        return web.HTTPNotFound()

    MEDIA_FILETYPES = [".mp4", ".gif", ".webp"]

    async def get_media(self, request):
        view = request.match_info['view']
        event = request.match_info['name']
        views_path = os.path.join('views', view)

        ammt = self._query_int(request, "value")
        return self.glob_var([views_path, "public/media"], event,
                             self.MEDIA_FILETYPES, ammt)

    async def post_shutdown(self, request):
        if self.shutdown_evt:
            self.shutdown_evt.set()
        return web.Response()

    async def get_command(self, request):
        try:
            cmd = race_commands.get_nowait()
            return web.json_response(cmd)
        except Empty:
            return web.Response(text="")

    async def post_replay(self, request):
        event = {}
        if request.content_type == 'application/x-www-form-urlencoded':
            data = await request.post()
            event = json.loads(data["payload"])
        else:
            event = await request.json()
        self.replay_queue.put(event)
        return web.Response()

    async def post_config(self, request):
        if not request.can_read_body:
            return web.json_response({"ok": False, "error": "No body"}, status=400)

        try:
            new_config = await request.json()
        except (json.JSONDecodeError, ValueError):
            return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)

        if not all(k in new_config for k in ("client_id", "username")) or \
                not any(k in new_config for k in ("oauth", "secret")):
            logger.error("Config not complete")
            return web.json_response({"ok": False, "error": "Config not complete"}, status=400)

        from ashnasbot.config import Config
        Config().update_many(new_config)
        if self.reload_evt:
            self.reload_evt.set()

        return web.json_response({"ok": True})

    async def post_prediction(self, request):
        event = {}
        if request.content_type == 'application/x-www-form-urlencoded':
            data = await request.post()
            event = json.loads(data["payload"])
        else:
            event = await request.json()

        api_client = TwitchClient()
        birds = json.loads(event['data'])
        birds = [f"{i+1}: {name}" for i, name in enumerate(birds)]
        res = await api_client.create_prediction(birds)
        if not res:
            return web.HTTPInternalServerError()

        db.ensure("chocobo_prediction", primary="prediction_id")

        birbs = json.dumps(res["birbs"])
        res["birbs"] = birbs
        keys = list(res.keys())
        db.update("chocobo_prediction", res, keys=keys)

        return web.Response()

    async def begin_auth(self, request):
        # Step 1
        scope = ["channel:bot", "channel:read:redemptions", "moderator:read:followers",
                 "channel:manage:predictions"]
        return_feature = request.query.get("feature", "chat")
        return_channel = request.query.get("channel", None)
        return_theme = request.query.get("theme", "noir")

        oauth = OAuth2Session(client_id=self.client_id, redirect_uri=redirect_uri, scope=scope)
        authorization_url, state = oauth.authorization_url(auth_base_url, force_verify=True)
        oauth.close()

        # Twitch echoes 'state' back to the callback, so the return target rides
        # along with the CSRF nonce — no shared server-side state, no locking.
        state = f"{state};{return_feature};{return_channel or ''};{return_theme}"
        authorization_url = _replace_state(authorization_url, state)

        # Session cookie only stores the nonce for CSRF verification.
        session = await new_session(request)
        session['state'] = state
        return aiohttp.web.HTTPFound(authorization_url)

    # Step 2 (On Twitch)

    async def auth_callback(self, request):
        """ Step 3: Retrieving an access token.

        The user has been redirected back from the provider to your registered
        callback URL. With this redirection comes an authorization code included
        in the redirect URL. We will use that to obtain an access token.
        """
        state = request.query.get('state', '')
        parts = state.split(";")
        if len(parts) != 4:
            logger.error("Auth callback with malformed state")
            return web.Response(text="Auth failed: bad state", status=400)
        _, return_feature, return_channel, return_theme = parts

        # CSRF check: if we still have the session cookie, the state must match.
        session = await get_session(request)
        if session.get('state') and session['state'] != state:
            logger.error("Auth callback state mismatch — possible CSRF, rejecting")
            return web.Response(text="Auth failed: state mismatch", status=400)

        code = request.query.get('code')
        if not code:
            logger.error("Auth callback missing code")
            url = f'/views/{return_theme}/{return_feature}.html?channel={return_channel}'
            return aiohttp.web.HTTPFound(url)

        body = urllib.parse.urlencode({'client_id': self.client_id,
                                       'client_secret': self.secret,
                                       'redirect_uri': redirect_uri})
        twitch = OAuth2Session(client_id=self.client_id, state=state)
        try:
            token = await asyncio.to_thread(twitch.fetch_token, token_url, code=code, body=body)
        except Exception:
            logger.exception("Failed to auth token")
            url = f'/views/{return_theme}/{return_feature}.html?channel={return_channel}'
            return aiohttp.web.HTTPFound(url)
        finally:
            twitch.close()

        # Resolve which Twitch login this token actually belongs to.
        login_for = None
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(
                    "https://id.twitch.tv/oauth2/validate",
                    headers={"Authorization": f"OAuth {token['access_token']}"}
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        login_for = data.get("login", "").lower() or None
        except Exception:
            pass
        if login_for and login_for != return_channel.lower():
            logger.warning(
                "Auth token is for '%s' but channel is '%s' — refusing to store",
                login_for, return_channel)
            url = (f'/views/{return_theme}/{return_feature}.html'
                   f'?channel={return_channel}&auth_error=wrong_account&auth_got={login_for}')
            return aiohttp.web.HTTPFound(url)

        # Persist channel token server-side so the server can refresh it automatically.
        from ashnasbot.twitch.db import ensure, update as db_update
        ensure("channel_tokens", "channel")
        db_update("channel_tokens", {
            "channel": return_channel,
            "access_token": token["access_token"],
            "refresh_token": token.get("refresh_token", ""),
            "login_for": login_for or return_channel.lower(),
        }, ["channel"])
        if self.reload_evt:
            self.reload_evt.set()

        resp = aiohttp.web.HTTPFound(f'/views/{return_theme}/{return_feature}.html?channel={return_channel}')
        resp.set_cookie('token', token["access_token"], max_age=int(token["expires_in"]), secure=True)
        resp.set_cookie('refresh', token["refresh_token"], secure=True)
        resp.set_cookie('auth_expires', token["expires_in"])
        return resp

    async def post_set_bot_token(self, request):
        """Set the bot token directly without a browser OAuth redirect.

        Accepts JSON {"token": "..."}.  If no token is supplied in the body the
        handler falls back to the value stored in config["oauth"] (stripping the
        leading "oauth:" prefix if present).  The token is validated against
        Twitch's introspection endpoint; on success the bot_token, bot_user_id
        and username config keys are updated.
        """
        token = None
        refresh_token = None
        try:
            body = await request.json()
            token = body.get("token", "").strip()
            refresh_token = body.get("refresh_token", "").strip() or None
        except Exception:
            pass

        if not token:
            from ashnasbot.config import Config
            oauth = Config().get("oauth", "")
            token = oauth.removeprefix("oauth:").strip()

        if not token:
            return web.json_response({"ok": False, "error": "No token provided"}, status=400)

        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(
                    "https://id.twitch.tv/oauth2/validate",
                    headers={"Authorization": f"OAuth {token}"}
                ) as resp:
                    if resp.status != 200:
                        return web.json_response(
                            {"ok": False, "error": "Token invalid or expired"}, status=400)
                    data = await resp.json()
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=500)

        bot_user_id = data.get("user_id")
        bot_username = data.get("login")
        scopes = data.get("scopes", [])

        from ashnasbot.config import Config
        cfg = Config()
        cfg.update("bot_token", token)
        cfg.update("bot_user_id", bot_user_id)
        cfg.update("username", bot_username)
        if refresh_token:
            cfg.update("bot_refresh_token", refresh_token)
            logger.info("Bot configured via token: %s (%s) scopes=%s (refresh token stored)",
                        bot_username, bot_user_id, scopes)
        else:
            logger.info("Bot configured via token: %s (%s) scopes=%s "
                        "(no refresh token — auto-renewal unavailable)",
                        bot_username, bot_user_id, scopes)

        if self.reload_evt:
            self.reload_evt.set()

        return web.json_response({
            "ok": True,
            "login": bot_username,
            "user_id": bot_user_id,
            "scopes": scopes,
        })

    async def begin_bot_auth(self, request):
        """Step 1 of bot account OAuth — redirect to Twitch."""
        scope = ["user:bot", "user:read:chat", "user:write:chat", "user:read:emotes"]
        oauth = OAuth2Session(client_id=self.client_id, redirect_uri=bot_redirect_uri, scope=scope)
        from ashnasbot.config import Config
        bot_login = Config().get("username", None)
        extra = {"force_verify": "true"}
        if bot_login:
            extra["login"] = bot_login
        authorization_url, state = oauth.authorization_url(auth_base_url, **extra)
        oauth.close()
        session = await new_session(request)
        session['bot_state'] = state
        return aiohttp.web.HTTPFound(authorization_url)

    async def bot_auth_callback(self, request):
        """Step 3 of bot account OAuth — exchange code, persist token + user ID."""
        state = request.query.get('state')
        session = await get_session(request)
        if session.get('bot_state') and state and session['bot_state'] != state:
            logger.error("Bot auth callback state mismatch — possible CSRF, rejecting")
            return web.Response(text="Bot auth failed: state mismatch", status=400)

        code = request.query.get('code')
        if not code:
            logger.error("Bot auth callback missing code")
            return web.Response(text="Bot auth failed: missing code", status=400)

        body = urllib.parse.urlencode({'client_id': self.client_id,
                                       'client_secret': self.secret,
                                       'redirect_uri': bot_redirect_uri})
        twitch = OAuth2Session(client_id=self.client_id, state=state)
        try:
            token = await asyncio.to_thread(twitch.fetch_token, token_url, code=code, body=body)
        except Exception:
            logger.exception("Failed to retrieve bot auth token")
            return web.Response(text="Bot auth failed", status=500)
        finally:
            twitch.close()

        access_token = token["access_token"]

        # Resolve the bot's user ID using the token itself
        bot_user_id = None
        bot_username = None
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(
                    "https://api.twitch.tv/helix/users",
                    headers={"Client-ID": self.client_id,
                             "Authorization": f"Bearer {access_token}"}
                ) as resp:
                    data = await resp.json()
                    bot_user_id = data["data"][0]["id"]
                    bot_username = data["data"][0]["login"]
        except Exception as e:
            logger.error("Failed to fetch bot user info: %s", e)
            return web.Response(text="Bot auth failed: could not resolve user", status=500)

        # Persist to config (in-memory + file)
        from ashnasbot.config import Config
        cfg = Config()
        cfg.update("bot_token", access_token)
        cfg.update("bot_refresh_token", token.get("refresh_token", ""))
        cfg.update("bot_user_id", bot_user_id)
        cfg.update("username", bot_username)
        logger.info("Bot account configured: %s (%s)", bot_username, bot_user_id)

        if self.reload_evt:
            self.reload_evt.set()

        return web.Response(text=f"Bot authenticated as {bot_username}. You can close this tab.")

    def glob_var(self, paths, stub, filter, num=0):
        # Paths = list of locations to check in order of preference
        logger.debug(f"looking for {stub}{num}{filter} in {paths}")
        matching_files = []
        if num == 0:
            matching_files = [list(Path(path).glob(stub + ".*")) for path in paths]
        else:
            # This is a glob, not a regex
            matching_files = [list(Path(path).glob(stub + r"[123456789]*" + ".*")) for path in paths]

        candidates = []
        for mgroup in matching_files:
            for match in mgroup:
                if match.suffix in filter:
                    m = re.search(r'\d+$', match.stem)
                    if m:
                        if not any([True for x in candidates if x[0] == m.group()]):
                            candidates.append((int(m.group()), match))
                    elif num == 0:
                        candidates.append((0, match))

        if not candidates:
            logger.debug(f"No Candidates found for {stub}{num}{filter}")
            return web.HTTPNotFound()

        candidates = sorted(candidates)
        logger.debug(f"Candidates: {candidates}")
        match = None
        matches = indices(candidates, num)
        if matches:
            # Exact match
            match = random.choice(matches)
            logger.debug(f"Found exact match(s) for glob {num}")
        else:
            # Find closest
            match = bisect.bisect_right(candidates, (num, )) - 1
            logger.debug(f"Found closest match for glob {num}")
        logger.debug(str(candidates[match]))
        return web.FileResponse(candidates[match][1])


def indices(lst, item):
    return [i for i, x in enumerate(lst) if x[0] == item]
