import asyncio
from asyncio import CancelledError as CancelledError
import contextvars
import json
import logging
from queue import Empty
from random import randrange
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
        while not self.shutdown_event.is_set():
            try:
                processing = False
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


            except websockets.exceptions.ConnectionClosed as e:
                logger.info(f"Connection closed {e.code}")

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
            finally:
                if processing:
                    processing = False
                    queue.task_done()

    async def config_listener(self):
        while not self.shutdown_event.is_set():
            await self.reload_event.wait()
            logger.info("Reloading config")
            self.load_clients()
            self.reload_event.clear()

    async def shutdown_listener(self):
        await self.shutdown_event.wait()
        logger.info("Shutdown Started")
        self.shutdown()

    async def disconnect_listener(self, ws, channel_client):
        await ws.wait_closed()
        logger.info("WS client disconnected")
        if "heartbeat" in channel_client:
            channel_client["heartbeat"].cancel()
        if "alert" in channel_client:
            channel_client["alert"].cancel()
        if "pubsub" in channel_client:
            channel_client["pubsub"].disconnect()

        # Sleep in case we're just refreshing
        await asyncio.sleep(5)

        channel = channel_client["channel"]
        self.channels[channel] = [s for s in self.channels[channel] if s["socket"].open]
        # We're the last client, disconnect chat and clear caches
        if not self.channels[channel]:
            self.chatbot.unsubscribe(channel)
            if channel in self.http_clients:
                del self.http_clients[channel]
        logger.debug("WS client disconnect cleanup complete")
        remaining_tasks = [task for task in asyncio.Task.all_tasks() if not task.done()]
        logger.debug("Remaining Tasks: %d", len(remaining_tasks))
        for t in remaining_tasks:
            logger.debug("               : %s", t)

    async def heartbeat(self, ws_in):
        try:
            while not self.shutdown_event.is_set():
                await asyncio.sleep(20)
                if ws_in.closed:
                    return
                await ws_in.ping()
        except CancelledError:
            pass

    async def followers(self, channel):
        await asyncio.sleep(10)
        while not self.shutdown_event.is_set():
            if not channel in self.http_clients:
                self.http_clients[channel] = TwitchClient(self.config["client_id"], channel)
            recent_followers = await self.http_clients[channel].get_new_followers()
            if not recent_followers: 
                await asyncio.sleep(80 + randrange(20))
                continue

            for nickname in recent_followers:
                evt_msg = {
                    'nickname': nickname,
                    'type' : "FOLLOW",
                    'channel': channel,
                    'tags': {
                        'system-msg': f"{nickname} followed the channel"
                    }
                }
                await self._event_queue.put(evt_msg)

            # Don't spam api
            await asyncio.sleep(80 + randrange(20))

    async def alerts(self):
        while not self.shutdown_event.is_set():
            try:
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
                    self.channels[channel] = [s for s in self.channels[channel] if not s["socket"].closed]
                    for s in self.channels[channel]:
                        await s["socket"].send(json.dumps(event))
                else:
                    logger.error("No channel for alert")
            except Exception as e:
                logger.error(e)
            finally:
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
        channel = ""
        channel_client = {
            "socket": ws_in,
            "clientId": ctx_client_id.get(str(uuid.uuid4()))
        }
        channel_client.update(commands)
        if "chat" in commands:
            channel = commands["chat"]
            if db.exists("banned")and db.find("banned", name=channel):
                logger.error(f"We are banned from {channel}")
                resp = {"type": "BANNED", "channel": channel}
                await ws_in.send(json.dumps(resp))
                return
            self.chatbot.subscribe(channel)
        if "alert" in commands:
            channel = commands['alert']
            alert_task = asyncio.create_task(self.followers(channel), name=f"{channel}_followers")
            channel_client["alert"] = alert_task
            tasks.append(alert_task)
        if "auth" in commands:
            # TODO: handle multiple cleanly
            channel = commands["chat"]
            if not channel in self.http_clients:
                self.http_clients[channel] = TwitchClient(self.config["client_id"], channel)
            channel_id = await self.http_clients[channel].get_channel_id(channel)
            token = commands["auth"]
            pubsub = PubSubClient(channel_id, token, self._event_queue)
            channel_client["pubsub"] = pubsub
            ps_conn = await pubsub.connect()
            tasks.append(asyncio.create_task(pubsub.heartbeat(ps_conn), name=f"{channel}_ps_hb"))
            tasks.append(asyncio.create_task(pubsub.receive_message(ps_conn), name=f"{channel}_ps_receive"))

        heartbeat_task = asyncio.create_task(self.heartbeat(ws_in), name=f"{channel}_hb")
        tasks.append(heartbeat_task)
        channel_client["heartbeat"] = heartbeat_task
        channel_client["channel"] = channel
        if channel in self.channels:
            self.channels[channel].append(channel_client)
        else:
            self.channels[channel] = [channel_client]

        self.loop.create_task(self.disconnect_listener(ws_in, channel_client), name=f"{channel}_dc_hdlr")

        logger.info(f"Socket client Join: {command}")
        await asyncio.gather(*tasks)
        logger.info(f"Socket client Leave: {command}")
        await ws_in.close()

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
        self.loop.create_task(self.chat(), name=f"chat")
        self.loop.create_task(self.alerts(), name=f"alert")
        self.loop.create_task(self.config_listener(), name=f"config")
        self.loop.create_task(self.shutdown_listener(), name=f"shutdown")

        self.webserver = WebServer(reload_evt=self.reload_event, loop=self.loop, shutdown_evt=self.shutdown_event,
                                   client_id=self.config["client_id"], secret=self.config["secret"])

        try:
            self.loop.run_forever()
        except KeyboardInterrupt:
            logger.info("Interrrupted")
            self.shutdown()
            logger.info("Done")
        logger.info("Ashnasbot Exited succesfully")
