import aiohttp
from aiohttp import web
import asyncio
import json
import logging
import dataset
import os
from requests_oauthlib import OAuth2Session

import base64
from cryptography import fernet
from aiohttp import web
import urllib.parse
from aiohttp_session import setup, get_session, new_session, session_middleware
from aiohttp_session.cookie_storage import EncryptedCookieStorage

logger = logging.getLogger(__name__)

db = dataset.connect('sqlite:///ashnasbot.db')

# OAuth Details
auth_base_url = 'https://id.twitch.tv/oauth2/authorize'
token_url = 'https://id.twitch.tv/oauth2/token'
redirect_uri = "http://localhost:8080/authorize"


os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"



class WebServer(object):
    def __init__(self, reload_evt=None, address='0.0.0.0', port=8080, loop=None, shutdown_evt=None,
                 client_id=None, secret=None):
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
        asyncio.ensure_future(self.start(), loop=self.loop)

    async def start(self):
        self.app = web.Application(loop=self.loop, debug=True)
        fernet_key = fernet.Fernet.generate_key()
        secret_key = base64.urlsafe_b64decode(fernet_key)
        setup(self.app, EncryptedCookieStorage(secret_key))
        self.setup_routes()
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, self.address, self.port)
        await self.site.start()
        logger.info('------ serving on %s:%d ------'
              % (self.address, self.port))

    @staticmethod
    async def get_dashboard(request):
        return web.HTTPFound('/static/config/dashboard.html')

    @staticmethod
    async def get_chat(request):
        return web.HTTPFound('/static/ff7/chat.html')

    @staticmethod
    async def get_favicon(request):
        return web.FileResponse('public/favicon.ico')

    def setup_routes(self):
        self.app.router.add_get('/api/config', self.get_config)
        self.app.router.add_post('/api/config', self.post_config)
        self.app.router.add_post('/api/shutdown', self.post_shutdown)
        self.app.router.add_static('/static', path="public/")

        # This is very important
        self.app.router.add_get('/favicon.ico', self.get_favicon)

        # Shortcuts
        self.app.router.add_get('/', self.get_dashboard)
        self.app.router.add_get('/dashboard', self.get_dashboard)
        self.app.router.add_get('/chat', self.get_chat)
        self.app.router.add_get('/user_auth', self.begin_auth)
        self.app.router.add_get('/authorize', self.auth_callback)

    @staticmethod
    async def get_config(request):
        with open('config.json', 'r') as config:
            config = json.load(config)
            del config["secret"]
            return web.json_response(config)
        return web.FileResponse('config.json')

    async def post_shutdown(self, request):
        if self.shutdown_evt:
            self.shutdown_evt.set()
        return web.Response()

    async def post_config(self, request):
        if request.can_read_body:
            with open('config.json', 'r+') as config:
                old_config = json.load(config)
                new_config = await request.json()
                if not all(k in new_config for k in ("client_id","oauth", "username")) or \
                    not all(k in new_config for k in ("client_id","secret", "username")):
                    logger.error("Config not complete")
                    return

                new_config = old_config.update(new_config)

                json.dump(new_config, config)
                if self.reload_evt:
                    self.reload_evt.set()

        return web.json_response({})

    async def begin_auth(self, request):
        # Step 1
        scope = ['channel:read:redemptions' ]
        oauth = OAuth2Session(client_id=self.client_id, redirect_uri=redirect_uri,
                            scope=scope)
        authorization_url, state = oauth.authorization_url(auth_base_url)
        return_channel = request.query.get("channel", None)

        state = f"{state};{return_channel}"

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

        body = urllib.parse.urlencode({'client_id': self.client_id, 'client_secret': self.secret, 'redirect_uri': redirect_uri})
        twitch = OAuth2Session(client_id=self.client_id, state=state)
        code = request.query['code']
        token = twitch.fetch_token(token_url, code=code, body=body)

        # At this point you can fetch protected resources but lets save
        # the token and show how this is done from a persisted token
        # in /profile.
        session['token'] = token
        state = session['state']
        return_channel = state.split(";")[1]

        resp = aiohttp.web.HTTPFound(f'/static/simple/chat.html?channel={return_channel}')
        resp.cookies['token'] = token["access_token"]
        return resp

if __name__ == '__main__':

    loop = asyncio.get_event_loop()
    logging.basicConfig(level=logging.DEBUG)
    loop.set_debug(False)
    ws = WebServer(loop=loop)
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        tasks = asyncio.gather(
                    *asyncio.Task.all_tasks(loop=loop),
                    loop=loop,
                    return_exceptions=True)
        tasks.add_done_callback(lambda t: loop.stop())
        tasks.cancel()
