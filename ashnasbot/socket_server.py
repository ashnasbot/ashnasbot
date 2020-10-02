import asyncio
from asyncio import CancelledError as CancelledError
from collections import deque
import contextvars
import json
import logging
from queue import Queue, Empty
from random import randrange
import time
from threading import Thread
import uuid
from concurrent.futures import ThreadPoolExecutor
import os

import websockets

from .async_http import WebServer
from .chat_bot import ChatBot
from .config import Config, ReloadException
from .twitch import db
from .twitch.pubsub import PubSubClient
from .twitch import handle_message, get_bits
from .twitch.api_client import TwitchClient
from .twitch.av import get_sound
from .twitch.commands import BannedException
from .users import Users

logger = logging.getLogger(__name__)
SCRAPE_AVATARS = True

logging.getLogger("websockets").setLevel(logging.INFO)
ctx_client_id = contextvars.ContextVar('client_id')

def filter_output(event, commands=False, **kwargs):
    if not "chat" in kwargs:
        if event["type"] == 'TWITCHCHATMESSAGE':
            return False
    if not "alert" in kwargs:
        if event["type"] != 'TWITCHCHATMESSAGE':
            return False
    return True

def allowed_content(event, commands=False, **kwargs):
    message = event.message if hasattr(event, "message") else ""
    if not commands:
        if message.startswith('!'):
            logger.debug("COMMAND %s (Ignored)", message)
            return False
    if not "chat" in kwargs:
        if event.type == 'TWITCHCHATMESSAGE':
            return False
    if not "alert" in kwargs:
        # RAID, HOST, SUBGIFT, SUB
        if event.type in ['TWITCHATUSERNOTICE', 'SUB', "RAID", "HOST"]:
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
        self.pubsub_clients = {}
        self.loop = None
        self.reload_event = None
        self.shutdown_event = None
        Thread.__init__(self)
        self.websocket_server = None
        self._event_queue = None
        self.recent_events = deque([], 20)
        self.replay_queue = Queue()

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
                    if event.type != 'TWITCHCHATMESSAGE':
                        self.recent_events.append(content)
                    elif "tags" in content and "bits" in content["tags"]:
                        bits_evt = get_bits(content)
                        self.recent_events.append(bits_evt)
                    if content:
                        if "tags" in content and any([s.get("images", None) for s in self.channels[channel]]):
                            if self.users:
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
    
    async def replay(self):
        while not self.shutdown_event.is_set():
            try:
                event = self.replay_queue.get_nowait()
                event["id"] = str(uuid.uuid4())  # Reset the id
                filename = "evtdmp.json"
                if os.path.exists(filename):
                    wr_flags = 'r+'
                else:
                    wr_flags = 'w+'
                with open(filename, wr_flags) as file:
                    try:
                        data = json.load(file)
                    except json.decoder.JSONDecodeError:
                        data = []
                    data.append(event)
                    file.seek(0)
                    json.dump(data, file, indent=2)
                if event["type"] == 'TWITCHCHATMESSAGE':
                    channel = event["channel"]
                    for s in self.channels[channel]:
                        if filter_output(event, **s):
                            await s["socket"].send(json.dumps(event, cls=MsgEncoder))
                else:
                    # Dont add_event as we've seen it before
                    await self._event_queue.put(event)
            except Empty:
                await asyncio.sleep(1)


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
            if hasattr(channel_client["alert"], "cancel"):
                channel_client["alert"].cancel()
        if "pubsub" in channel_client:
            await channel_client["pubsub"].disconnect()

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
                try:
                    self.http_clients[channel] = TwitchClient(self.config["client_id"], channel)
                except:
                    return
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
                        'system-msg': f"{nickname} followed the channel",
                        'tmi-sent-ts': str(int(time.time())) + "000",
                        'display-name': nickname
                    }
                }
                await self.add_alert(evt_msg)

            # Don't spam api
            await asyncio.sleep(80 + randrange(20))

    async def add_alert(self, evt):
        self.recent_events.append(evt)
        await self._event_queue.put(evt)

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
                elif channel is None:
                    # This is a broadcast
                    for c in self.channels:
                        for s in self.channels[c]:
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
        channel = commands["channel"]
        if "chat" in commands:
            if db.exists("banned")and db.find("banned", name=channel):
                logger.error(f"We are banned from {channel}")
                resp = {"type": "BANNED", "channel": channel}
                await ws_in.send(json.dumps(resp))
                return
            self.chatbot.subscribe(channel)
        if "auth" in commands:
            try:
                if not channel in self.http_clients:
                    self.http_clients[channel] = TwitchClient(self.config["client_id"], channel)
                if channel in self.pubsub_clients:
                    pubsub = self.pubsub_clients[channel]
                    channel_client["pubsub"] = pubsub
                    await pubsub.connect()
                else:
                    channel_id = await self.http_clients[channel].get_channel_id(channel)
                    token = commands["auth"]
                    pubsub = PubSubClient(channel, channel_id, token, self.add_alert)
                    self.pubsub_clients[channel] = pubsub
                    channel_client["pubsub"] = pubsub
                    ps_conn = await pubsub.connect()
                    tasks.append(self.make_task(pubsub.heartbeat(ps_conn), name=f"{channel}_ps_hb"))
                    tasks.append(self.make_task(pubsub.receive_message(ps_conn), name=f"{channel}_ps_receive"))
            except ValueError:
                pass
        elif "alert" in commands:
            # No auth, so poll for follows
            alert_task = self.make_task(self.followers(channel), name=f"{channel}_followers")
            channel_client["alert"] = alert_task
            tasks.append(alert_task)
            self.chatbot.subscribe(channel)

        heartbeat_task = self.make_task(self.heartbeat(ws_in), name=f"{channel}_hb")
        tasks.append(heartbeat_task)
        channel_client["heartbeat"] = heartbeat_task
        channel_client["channel"] = channel
        if channel in self.channels:
            self.channels[channel].append(channel_client)
        else:
            self.channels[channel] = [channel_client]

        self.make_task(self.disconnect_listener(ws_in, channel_client), name=f"{channel}_dc_hdlr")

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

    def make_task(self, func, name):
        try:
            return self.loop.create_task(func, name=name)
        except TypeError:
            return self.loop.create_task(func)


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
        secret = self.config.get("secret", None)
        client_id = self.config.get("client_id", None)
        oauth = self.config.get("oauth", None)
        user = self.config.get("username", None)

        if user and oauth:
            self.chatbot = ChatBot(self.loop, user, oauth)
        else:
            logger.warning("No user/oauth - Chat unavailable")
        
        if client_id:
            try:
                self.users = Users(TwitchClient(client_id, ''))
            except ValueError:
                logger.warning("No client secret - API unavilable")
        else:
            logger.warning("No client ID - API unavilable")

        self.reload_event = asyncio.Event()
        self.shutdown_event = asyncio.Event()
        self.make_task(self.chat(), name=f"chat")
        self.make_task(self.alerts(), name=f"alert")
        self.make_task(self.config_listener(), name=f"config")
        self.make_task(self.shutdown_listener(), name=f"shutdown")
        self.make_task(self.replay(), name=f"event_replay")

        self.webserver = WebServer(reload_evt=self.reload_event, loop=self.loop, shutdown_evt=self.shutdown_event,
                                   client_id=client_id, secret=secret, events=self.recent_events,
                                   replay=self.replay_queue)

        try:
            self.loop.run_forever()
        except KeyboardInterrupt:
            logger.info("Interrrupted")
            self.shutdown()
            logger.info("Done")
        logger.info("Ashnasbot shutdown complete")
