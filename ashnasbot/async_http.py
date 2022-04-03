import aiohttp
import asyncio
import bisect
import json
import logging
import dataset
import os
from pathlib import Path
import re
from requests_oauthlib import OAuth2Session

import base64
from cryptography import fernet
from aiohttp import web
import urllib.parse
from aiohttp_session import setup, get_session, new_session
from aiohttp_session.cookie_storage import EncryptedCookieStorage

from ashnasbot.twitch import pokedex

logger = logging.getLogger(__name__)

db = dataset.connect('sqlite:///ashnasbot.db')

# OAuth Details
auth_base_url = 'https://id.twitch.tv/oauth2/authorize'
token_url = 'https://id.twitch.tv/oauth2/token'
redirect_uri = "http://localhost:8080/authorize"


os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

LOG_FORMAT = "%s %r %a"


class WebServer(object):
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
        loop.create_task(self.start())

    async def start(self):
        self.app = web.Application(loop=self.loop, logger=logger)
        fernet_key = fernet.Fernet.generate_key()
        secret_key = base64.urlsafe_b64decode(fernet_key)
        setup(self.app, EncryptedCookieStorage(secret_key))
        self.setup_routes()
        self.runner = web.AppRunner(self.app, access_log_format=LOG_FORMAT)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, self.address, self.port)
        await self.site.start()
        logger.info('------ serving on %s:%d ------' % (self.address, self.port))

    @staticmethod
    async def get_dashboard(request):
        return web.HTTPFound('/static/config/dashboard.html')

    @staticmethod
    async def get_chat(request):
        return web.HTTPFound('/static/base/chat.html')

    @staticmethod
    async def get_favicon(request):
        return web.FileResponse('public/favicon.ico')

    def setup_routes(self):
        # API
        self.app.router.add_get('/api/config', self.get_config)
        self.app.router.add_get('/api/views', self.get_views)
        self.app.router.add_get('/res/{view}/sound/{event}', self.get_sound)
        self.app.router.add_get('/res/{view}/image/{name}', self.get_image)
        self.app.router.add_post('/api/config', self.post_config)
        self.app.router.add_post('/api/shutdown', self.post_shutdown)
        self.app.router.add_post('/replay_event', self.post_replay)

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

        # API
        self.app.router.add_get('/dex', self.get_pokedex)

    @staticmethod
    async def get_config(request):
        with open('config.json', 'r') as config:
            config = json.load(config)
            del config["secret"]
            return web.json_response(config)

    @staticmethod
    async def get_views(request):
        resp = []
        for path in os.scandir("views"):
            if path.is_dir():
                if any([f.is_file() and f.name == "chat.html" for f in os.scandir(path.path)]):
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
        # # TODO: This
        # query = request.query_string
        # if query:
        #    logger.error(query)
        views_path = os.path.join('views', view)

        query = request.query
        if query and "value" in query:
            ammt = query["value"]

            # find exact
            views_match = list(Path(views_path).glob(event + ammt + ".*"))
            for match in views_match:
                if match.suffix in self.AUDIO_FILETYPES:
                    return web.FileResponse(views_match[0])

            fallback_match = list(Path("public/audio").glob(event + ammt + ".*"))
            for match in fallback_match:
                if match.suffix in self.AUDIO_FILETYPES:
                    return web.FileResponse(fallback_match[0])

            # find closest
            views_match = list(Path(views_path).glob(event))
            candidates = []
            for match in views_match:
                if match.suffix in self.AUDIO_FILETYPES:
                    m = re.search(r'\d+$', match.stem)
                    if m:
                        candidates.append((m.group(), match))
            if candidates:
                match = bisect.bisect_right(candidates, ammt)
                return web.FileResponse(candidates[0])

            fallback_match = list(Path("public/audio").glob(event))
            for match in fallback_match:
                if match.suffix in self.AUDIO_FILETYPES:
                    m = re.search(r'\d+$', match.stem)
                    if m:
                        candidates.append((m.group(), match))
            if candidates:
                match = bisect.bisect_right(candidates, ammt)
                return web.FileResponse(candidates[0])

        else:
            views_match = list(Path(views_path).glob(event + ".*"))
            for match in views_match:
                if match.suffix in self.AUDIO_FILETYPES:
                    return web.FileResponse(views_match[0])

            fallback_match = list(Path("public/audio").glob(event + ".*"))
            for match in fallback_match:
                if match.suffix in self.AUDIO_FILETYPES:
                    return web.FileResponse(fallback_match[0])

        return web.HTTPNotFound()

    IMAGE_FILETYPES = [".png"]

    async def get_image(self, request):
        view = request.match_info['view']
        name = request.match_info['name']

        views_path = os.path.join('views', view)
        views_match = list(Path(views_path).glob(name + ".*"))

        for match in views_match:
            if match.suffix in self.IMAGE_FILETYPES:
                return web.FileResponse(views_match[0])

        fallback_match = list(Path("public/images").glob(name + ".*"))
        for match in fallback_match:
            if match.suffix in self.IMAGE_FILETYPES:
                return web.FileResponse(fallback_match[0])

        return web.HTTPNotFound()

    async def post_shutdown(self, request):
        if self.shutdown_evt:
            self.shutdown_evt.set()
        return web.Response()

    async def post_replay(self, request):
        event = await request.json()
        self.replay_queue.put(event)
        return web.Response()

    async def post_config(self, request):
        if request.can_read_body:
            with open('config.json', 'r+') as config:
                old_config = json.load(config)
                new_config = await request.json()
                if not all(k in new_config for k in ("client_id", "oauth", "username")) or \
                        not all(k in new_config for k in ("client_id", "secret", "username")):
                    logger.error("Config not complete")
                    return

                new_config = old_config.update(new_config)

                json.dump(new_config, config)
                if self.reload_evt:
                    self.reload_evt.set()

        return web.json_response({})

    async def begin_auth(self, request):
        # Step 1
        scope = []
        oauth = OAuth2Session(client_id=self.client_id, redirect_uri=redirect_uri, scope=scope)
        authorization_url, state = oauth.authorization_url(auth_base_url, force_verify=True)
        return_channel = request.query.get("channel", None)
        return_theme = request.query.get("theme", "noir")

        state = f"{state};{return_channel};{return_theme}"

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
        session = await get_session(request)
        state = session['state']

        body = urllib.parse.urlencode({'client_id': self.client_id,
                                       'client_secret': self.secret,
                                       'redirect_uri': redirect_uri})
        twitch = OAuth2Session(client_id=self.client_id, state=state)
        code = request.query['code']
        token = twitch.fetch_token(token_url, code=code, body=body)

        # At this point you can fetch protected resources, lets save the token
        session['token'] = token
        state = session['state']
        return_channel = state.split(";")[1]
        return_theme = state.split(";")[2]

        resp = aiohttp.web.HTTPFound(f'/views/{return_theme}/chat.html?channel={return_channel}')
        resp.cookies['token'] = token["access_token"]
        return resp

    def get_pokedex(self, request):
        player = request.query['channel']
        resp = {}
        dex = pokedex.get_player_pokedex(player)
        for row in dex:
            resp[row['id']] = row['caught']
        return web.json_response(resp)
