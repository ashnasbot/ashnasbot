import asyncio
import json
import logging
from queue import Empty
import time
from threading import Thread
from concurrent.futures import ThreadPoolExecutor

import websockets

from .av import get_sound
from .async_http import WebServer
from .chat_bot import ChatBot
from .config import Config, ReloadException
from .twitch import handle_message
from .twitch_client import TwitchClient
from .users import Users

logger = logging.getLogger(__name__)
SCRAPE_AVATARS = True

logging.getLogger("websockets").setLevel(logging.INFO)


class SocketServer(Thread):

    def __init__(self):
        self.websockets = {}
        self.chatbot = None
        self.users = None
        self.http_clients = {}
        self.loop = None
        self.reload_event = None
        self.shutdown_event = None
        Thread.__init__(self)
        self._event_queue = None
        self.websocket_server = None

    async def chat(self):
        queue = None 
        while True:
            try:
                processing = False
                if self.shutdown_event.is_set():
                    return
                if not self.chatbot:
                    await asyncio.sleep(1)
                    continue

                queue = self.chatbot.chat()
                event = await queue.get()
                processing = True
                channel = event.channel
                if channel and channel not in self.websockets:
                    logger.error(f"Message for channel '{channel}' but no socket")
                    self.chatbot.unsubscribe(channel)
                if event: 
                    content = await handle_message(event)
                    if content:
                        if "tags" in content and SCRAPE_AVATARS:
                            content['logo'] = await self.users.get_picture(content['tags']['user-id'])
                        if channel:
                            self.websockets[channel] = [s for s in self.websockets[channel] if not s.closed]
                            for s in self.websockets[channel]:
                                await s.send(json.dumps(content))
                        else:
                            for c in self.websockets:
                                for s in self.websockets[c]:
                                    await s.send(json.dumps(content))

                processing = False
                queue.task_done()


            except websockets.exceptions.ConnectionClosed as e:
                logger.info(f"Connection closed {e.code}")
                if processing:
                    queue.task_done()

            except Exception as e:
                import traceback
                err = traceback.format_exc()
                logger.error(f"Failed to get chat: {e}")
                logger.debug(err)
                if processing:
                    queue.task_done()

    async def chat_alerts(self):
        queue = None
        while True:
            if self.shutdown_event.is_set():
                return

            if not self.chatbot:
                await asyncio.sleep(1)
                continue

            queue = self.chatbot.alerts()
            event = await queue.get()
            if event: 
                content = await handle_message(event)
                if content:
                    await self._event_queue.put(content)
            queue.task_done()

    async def config_listener(self):
        while True:
            if self.shutdown_event.is_set():
                return
            await self.reload_event.wait()
            logger.info("Reloading config")
            self.load_clients()
            self.reload_event.clear()

    async def shutdown_listener(self):
        await self.shutdown_event.wait()
        logger.info("Shutdown Started")
        self.shutdown()

    async def heartbeat(self, websocket):
        try:
            while True:
                if self.shutdown_event.is_set():
                    return
                await asyncio.sleep(20)
                if websocket.closed:
                    return
                await websocket.ping()
        except asyncio.CancelledError:
            pass

    async def followers(self, channel):
        await asyncio.sleep(60)
        while True:
            if self.shutdown_event.is_set():
                return
            if not channel in self.http_clients:
                self.http_clients[channel] = TwitchClient(self.config["client_id"], channel)
            recent_followers = await self.http_clients[channel].get_new_followers()
            if not recent_followers: 
                await asyncio.sleep(80)
                continue

            for nickname in recent_followers:
                evt_msg = {
                    'nickname': nickname,
                    'type' : "FOLLOW",
                    'channel': channel
                }

                await self._event_queue.put(evt_msg)
            # Don't spam api
            await asyncio.sleep(80)

    async def alerts(self):
        while True:
            if self.shutdown_event.is_set():
                return
            event = await self._event_queue.get()
            if event is None:
                logger.info("No more alerts")
                return
            try:
                channel = event['channel']
            except KeyError:
                channel = event.channel
            if event['type'] == "FOLLOW":
                event['audio'] = get_sound("Mana_got_item")
            if event['type'] == "SUB":
                event['audio'] = get_sound("Super_Nintendo_Chalmers")

            if channel:
                self.websockets[channel] = [s for s in self.websockets[channel] if not s.closed]
                for s in self.websockets[channel]:
                    await s.send(json.dumps(event))
            else:
                logger.error("No channel for alert")

            self._event_queue.task_done()
            await asyncio.sleep(30)

    async def handle_connect(self, websocket, path):
        try:
            command = await websocket.recv()
        except:
            return
        if self.shutdown_event.is_set():
            return
        logger.info(command)

        commands = json.loads(command)

        tasks = []
        if "chat" in commands:
            channel = commands["chat"]
            self.chatbot.subscribe(channel)
            if channel in self.websockets:
                self.websockets[channel].append(websocket)
            else:
                self.websockets[channel] = [websocket]
        if "alert" in commands:
            channel = commands['alert']
            tasks.append(asyncio.create_task(self.followers(channel)))
        tasks.append(asyncio.create_task(self.heartbeat(websocket)))

        logger.info(f"Socket client Join: {command}")
        await asyncio.gather(*tasks)
        logger.info(f"Socket client Leave: {command}")
        websocket.close()
        self.websockets[channel] = [s for s in self.websockets[channel] if s.open]
        if not self.websockets[channel]:
            self.chatbot.unsubscribe(channel)

    def shutdown(self):
        logger.info("Shutting down server")
        self.websocket_server.close()
        self.websocket_server.wait_closed()
        for task in asyncio.Task.all_tasks():
            task.cancel()
        logger.info("Stopping loop")
        self.loop.stop()

    def load_clients(self):
        config = Config()
        try:
            self.config = config
        except KeyError as e:
            logger.error(f"Missing config ({e})")
            logger.error("Go to 'http://localhost:8080' to set")

    def run(self):
        logger.info("Starting socket server")
        self.loop = asyncio.new_event_loop()
        self.loop.set_default_executor(ThreadPoolExecutor(max_workers=5))
        self._event_queue = asyncio.Queue(loop=self.loop)
        asyncio.set_event_loop(self.loop)
        self.loop.set_debug(enabled=False)
        start_server = websockets.serve(self.handle_connect, '0.0.0.0', 8765)
        self.websocket_server = self.loop.run_until_complete(start_server)


        self.load_clients()
        self.chatbot = ChatBot(self.loop, self.config["username"], self.config["oauth"])
        self.users = Users(TwitchClient(self.config["client_id"], ''))
        self.reload_event = asyncio.Event()
        self.shutdown_event = asyncio.Event()
        self.loop.create_task(self.chat())
        self.loop.create_task(self.chat_alerts())
        self.loop.create_task(self.alerts())
        self.loop.create_task(self.config_listener())
        self.loop.create_task(self.shutdown_listener())

        WebServer(reload_evt=self.reload_event, loop=self.loop, shutdown_evt=self.shutdown_event)
        try:
            self.loop.run_forever()
        except KeyboardInterrupt:
            logger.info("Interrrupted")
            self.shutdown()
            logger.info("Done")
        logger.info("Ashnasbot Exited succesfully")
