from aiohttp import web
import asyncio
import json

class WebServer(object):
    def __init__(self, address='127.0.0.1', port=8080, loop=None):
        self.address = address
        self.port = port
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
        print('------ serving on %s:%d ------'
              % (self.address, self.port))

    def setup_routes(self):
        self.app.router.add_get('/api/config', self.get_config)
        self.app.router.add_post('/api/config', self.post_config)
        self.app.router.add_static('/static', path="public/")

    @staticmethod
    async def get_config(request):
        return web.FileResponse('config.json')

    @staticmethod
    async def post_config(request):
        # TODO: validate
        if request.can_read_body:
            with open('config.json', 'w') as config:
                new_config = await request.json()
                json.dump(new_config, config)

        return web.json_response({})

if __name__ == '__main__':
    import logging

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