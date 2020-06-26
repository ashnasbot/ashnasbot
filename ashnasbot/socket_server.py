import asyncio
import contextvars
import json
import logging
from queue import Empty
import time
from threading import Thread
import uuid
from concurrent.futures import ThreadPoolExecutor

import websockets

from .async_http import WebServer
from .chat_bot import ChatBot
from .config import Config, ReloadException
from .twitch import db
from .twitch.pubsub import PubSubClient
from .twitch import handle_message
from .twitch.api_client import TwitchClient
from .twitch.av import get_sound
from .twitch.commands import BannedException
from .users import Users

logger = logging.getLogger(__name__)
SCRAPE_AVATARS = True

logging.getLogger("websockets").setLevel(logging.INFO)
ctx_client_id = contextvars.ContextVar('client_id')

def filter_output(message, commands=False, **kwargs):
    return True

def allowed_content(event, commands=False, **kwargs):
    message = event.message if hasattr(event, "message") else ""
    if not commands:
        if message.startswith('!'):
            logger.debug("COMMAND %s (Ignored)", message)
            return False
    return True

def strip_content(content):
    return content

# TODO: make this serialisation useful in the client
class MsgEncoder(json.JSONEncoder):
    def default(self, obj): # pylint: disable=method-hidden
        if obj.__class__.__name__ in ["PRIV"]:
            return {"__enum__": str(obj)}
        return json.JSONEncoder.default(self, obj)
    
class SocketServer(Thread):

    def __init__(self):
        self.channels = {}
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
                if channel and channel not in self.channels:
                    logger.error(f"Message for channel '{channel}' but no socket")
                    self.chatbot.unsubscribe(channel)
                # TODO: refactor - this breaks broadcasts (DELETE)
                if event and channel and any([allowed_content(event, **s) for s in self.channels[channel]]):
                    content = await handle_message(event)
                    if content:
                        if "tags" in content and any([s.get("images", None) for s in self.channels[channel]]):
                            content['logo'] = await self.users.get_picture(content['tags']['user-id'])
                        if 'tags' in content and 'response' in content['tags']:
                            self.chatbot.send_message(content['message'], channel)
                        self.channels[channel] = [s for s in self.channels[channel] if not s["socket"].closed]
                        for s in self.channels[channel]:
                            if filter_output(content, **s):
                                await s["socket"].send(json.dumps(content, cls=MsgEncoder))
                elif not channel:
                    content = await handle_message(event)
                    for c in self.channels:
                        for s in self.channels[c]:
                            # TODO: Do we need global resp too?
                            await s["socket"].send(json.dumps(content))

                processing = False
                queue.task_done()


            except websockets.exceptions.ConnectionClosed as e:
                logger.info(f"Connection closed {e.code}")
                if processing:
                    queue.task_done()

            except BannedException as e:
                logger.warning("We have been banned from this channel")
                if not db.exists("banned"):
                    db.create("banned", primary=["name"])
                db.update("banned", {"name": e.channel}, ["name"])
                self.chatbot.unsubscribe(channel)

            except Exception as e:
                import traceback
                import os.path
                err = traceback.format_exc()
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

    async def heartbeat(self, ws_in):
        try:
            while True:
                if self.shutdown_event.is_set():
                    return
                await asyncio.sleep(20)
                if ws_in.closed:
                    return
                await ws_in.ping()
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

    async def events(self):
        while True:
            try:
                queue = self.webserver.events()
                event = await queue.get()
                channel = event['channel']
                if channel:
                    self.channels[channel] = [s for s in self.channels[channel] if not s.socket.closed]
                    for s in self.channels[channel]:
                        await s.socket.send(json.dumps(event))
                else:
                    logger.error("No channel for alert")
                self.queue.task_done()
            except:
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
                self.channels[channel] = [s for s in self.channels[channel] if not s.socket.closed]
                for s in self.channels[channel]:
                    await s.socket.send(json.dumps(event))
            else:
                logger.error("No channel for alert")

            self._event_queue.task_done()
            await asyncio.sleep(30)

    async def handle_connect(self, ws_in, path):
        try:
            command = await ws_in.recv()
        except:
            return
        if self.shutdown_event.is_set():
            return
        logger.info(command)

        commands = json.loads(command)

        tasks = []
        if "chat" in commands:
            channel = commands["chat"]
            if db.exists("banned")and db.find("banned", name=channel):
                logger.error(f"We are banned from {channel}")
                resp = {"type": "BANNED", "channel": channel}
                await ws_in.send(json.dumps(resp))
                return
            self.chatbot.subscribe(channel)
            channel_client = {
                "socket": ws_in,
                "clientId": ctx_client_id.get(str(uuid.uuid4()))
            }
            channel_client.update(commands)
            # TODO: self.webserver.register_callback()
            if channel in self.channels:
                self.channels[channel].append(channel_client)
            else:
                self.channels[channel] = [channel_client]
        if "alert" in commands:
            channel = commands['alert']
            tasks.append(asyncio.create_task(self.followers(channel)))
        if "oauth" in commands:
            channel = commands["chat"]
            channel_id = await TwitchClient(self.config["client_id"], '').get_channel_id(channel)
            print(channel_id)
            token = commands["oauth"]
            self.pubsub = PubSubClient(channel_id, token, self._event_queue)
            ps_conn = await self.pubsub.connect()
            self.loop.create_task(self.pubsub.heartbeat(ps_conn))
            self.loop.create_task(self.pubsub.receiveMessage(ps_conn))
            

        tasks.append(asyncio.create_task(self.heartbeat(ws_in)))

        logger.info(f"Socket client Join: {command}")
        await asyncio.gather(*tasks)
        logger.info(f"Socket client Leave: {command}")
        await ws_in.close()
        self.channels[channel] = [s for s in self.channels[channel] if s["socket"].open]
        if not self.channels[channel]:
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
        if self.config["oauth"]:
            self.chatbot = ChatBot(self.loop, self.config["username"], self.config["oauth"])
        self.users = Users(TwitchClient(self.config["client_id"], ''))
        self.reload_event = asyncio.Event()
        self.shutdown_event = asyncio.Event()
        self.loop.create_task(self.chat())
        self.loop.create_task(self.chat_alerts())
        self.loop.create_task(self.alerts())
        self.loop.create_task(self.config_listener())
        self.loop.create_task(self.shutdown_listener())

        self.loop.create_task(self.events())


        self.webserver = WebServer(reload_evt=self.reload_event, loop=self.loop, shutdown_evt=self.shutdown_event,
                                   client_id=self.config["client_id"], secret=self.config["secret"])

        try:
            self.loop.run_forever()
        except KeyboardInterrupt:
            logger.info("Interrrupted")
            self.shutdown()
            logger.info("Done")
        logger.info("Ashnasbot Exited succesfully")
