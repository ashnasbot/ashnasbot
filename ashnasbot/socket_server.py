import asyncio
import json
import logging
from queue import Empty
import time
from threading import Thread

import websockets

from .av import get_sound
from .async_http import WebServer
from .chat_bot import ChatBot
from .config import ConfigLoader, ReloadException
from .twitch import handle_message
from .twitch_client import TwitchClient

logger = logging.getLogger(__name__)


class SocketServer(Thread):

    def __init__(self):
        self.chatbot = None
        self.http_client = None
        self.loop = None
        self.reload_event = None
        self.shutdown_event = None
        Thread.__init__(self)
        self._event_queue = None
        self.websocket_server = None

    async def chat(self, websocket):
        try:
            while True:
                if self.shutdown_event.is_set():
                    return
                # Ping to minimise messages being thrown away
                try:
                    await websocket.ping()
                except asyncio.CancelledError:
                    pass
                if websocket.closed:
                    return
                if not self.chatbot:
                    return
                events = self.chatbot.get_chat_messages()
                if not events: 
                    await asyncio.sleep(0.2)
                    continue

                for event in events:
                    content = handle_message(event)
                    if content:
                        await websocket.send(json.dumps(content))
        except Exception as e:
            logger.info(f"Failed to get chat: {e}")

    async def chat_alerts(self):
        while True:
            if self.shutdown_event.is_set():
                return
            events = self.chatbot.get_chat_alerts()
            if not events: 
                await asyncio.sleep(3)
                continue

            for event in events:
                content = handle_message(event)
                if content:
                    await self._event_queue.put(content)

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

    async def followers(self):
        await asyncio.sleep(60)
        while True:
            if self.shutdown_event.is_set():
                return
            if not self.http_client:
                return
            recent_followers = await self.http_client.get_new_followers()
            if not recent_followers: 
                await asyncio.sleep(80)
                continue

            for nickname in recent_followers:
                evt_msg = {
                    'nickname': nickname,
                    'type' : "FOLLOW"
                }

                await self._event_queue.put(evt_msg)
            # Don't spam api
            await asyncio.sleep(80)

    async def alerts(self, websocket):
        while True:
            if self.shutdown_event.is_set():
                return
            event = await self._event_queue.get()
            if event is None:
                logger.info("No more alerts")
                return
            if event['type'] == "FOLLOW":
                event['audio'] = get_sound("Mana_got_item")
            if event['type'] == "SUB":
                event['audio'] = get_sound("Super_Nintendo_Chalmers")

            logger.info(event)

            await websocket.send(json.dumps(event))

            self._event_queue.task_done()
            await asyncio.sleep(30)


    async def handle_connect(self, websocket, path):
        try:
            command = await websocket.recv()
        except:
            return
        if self.shutdown_event.is_set():
            return

        commands = command.split(",")
        tasks = []
        if "chat" in commands:
            tasks.append(asyncio.create_task(self.chat(websocket)))
        if "alert" in commands:
            tasks.append(asyncio.create_task(self.chat_alerts()))
            tasks.append(asyncio.create_task(self.followers()))
            tasks.append(asyncio.create_task(self.alerts(websocket)))
        if not tasks:
            return
        tasks.append(asyncio.create_task(self.heartbeat(websocket)))

        logger.info(f"Socket client Join: {command}")
        await asyncio.gather(*tasks)
        logger.info(f"Socket client Leave: {command}")

    def shutdown(self):
        self.websocket_server.close()
        self.websocket_server.wait_closed()
        self.loop.stop()

    def load_clients(self):
        config = ConfigLoader().load()
        try:
            self.http_client = TwitchClient(config["client_id"], config["channel"])
            self.chatbot = ChatBot(config["channel"], config["username"], config["oauth"])
        except KeyError as e:
            logger.error(f"Missing config ({e})")
            logger.error("Go to 'http://localhost:8080' to set")

    def run(self):
        logger.info("Starting socket server")
        self.loop = asyncio.new_event_loop()
        self._event_queue = asyncio.Queue(loop=self.loop)
        asyncio.set_event_loop(self.loop)
        self.loop.set_debug(True)
        self.loop.set_debug(enabled=True)
        start_server = websockets.serve(self.handle_connect, '0.0.0.0', 8765)
        self.websocket_server = self.loop.run_until_complete(start_server)

        self.load_clients()
        self.reload_event = asyncio.Event()
        self.shutdown_event = asyncio.Event()
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
