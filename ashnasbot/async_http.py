from aiohttp import web
import asyncio
import json
import logging

logger = logging.getLogger(__name__)


class WebServer(object):
    def __init__(self, reload_evt=None, address='0.0.0.0', port=8080, loop=None, shutdown_evt=None):
        self.address = address
        self.port = port
        self.reload_evt = reload_evt
        self.shutdown_evt = shutdown_evt
        if loop is None:
            loop = asyncio.get_event_loop()
        self.loop = loop
        self.site = None
        asyncio.ensure_future(self.start(), loop=self.loop)

    async def start(self):
        self.app = web.Application(loop=self.loop, debug=True)
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

    @staticmethod
    async def get_config(request):
        return web.FileResponse('config.json')

    async def post_shutdown(self, request):
        if self.shutdown_evt:
            self.shutdown_evt.set()
        return web.Response()

    async def post_config(self, request):
        if request.can_read_body:
            with open('config.json', 'w') as config:
                new_config = await request.json()
                if not all(k in new_config for k in ("client_id","oauth", "username")):
                    logger.error("Config not complete")
                    return
                json.dump(new_config, config)
                if self.reload_evt:
                    self.reload_evt.set()

        return web.json_response({})

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
