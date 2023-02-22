import asyncio
from asyncio import CancelledError as CancelledError
from collections import deque
import contextvars
import json
import logging
from queue import Queue, Empty
from random import randrange
import uuid
from concurrent.futures import ThreadPoolExecutor

import websockets
from prometheus_client import Gauge, Counter
from prometheus_async.aio import track_inprogress


from .async_http import WebServer
from .chat_bot import ChatBot
from .config import Config
from .twitch import OWN_EMOTES, db, handle_message, get_bits, render_own_emotes, render_badges, cleanup
from .twitch.chatter import ChatChatter
from .twitch.data import OutputMessage, create_follower, event_from_output
from .twitch.pubsub import PubSubClient
from .twitch.api_client import TwitchClient
from .twitch.commands import BannedException
from .users import Users

logger = logging.getLogger(__name__)

logging.getLogger("websockets").setLevel(logging.INFO)
ctx_client_id = contextvars.ContextVar('client_id')


# Metrics
METRIC_CLIENTS = Gauge("clients", "Current client sessions")
METRIC_MESSAGES = Counter("messages", "Number of messages received", ["channel"])
METRIC_COMMANDS = Counter("commands", "Number of commands processed", ["channel"])
METRIC_SUBS = Counter("subscriptions", "Number of subscriptions received", ["channel"])
METRIC_FOLLOWS = Counter("followers", "Number of new followers received", ["channel"])
METRIC_REDEMPTION = Counter("redemptions", "Number of redemption messages received", ["channel"])
METRIC_EMOTES = Counter("emotes", "Number of emotes used in messages", ["channel"])


def update_event_metrics(event):
    c = event.channel

    match event.type:
        case 'SUB':
            METRIC_SUBS.labels(c).inc()
        case 'FOLLOW':
            METRIC_FOLLOWS.labels(c).inc()
        case 'REDEMPTION':
            METRIC_REDEMPTION.labels(c).inc()
    if "emotes" in event.tags and event.tags["emotes"]:
        METRIC_EMOTES.labels(c).inc(len(event.tags["emotes"].split(",")))


def filter_output(event, commands=False, **kwargs):
    if "chat" not in kwargs:
        if event["type"] == 'TWITCHCHATMESSAGE':
            return False
    elif "pubsub" in kwargs:
        if "tags" in event and "custom-reward-id" in event["tags"]:
            return False
    if "alert" not in kwargs:
        if event["type"] not in ['TWITCHCHATMESSAGE', 'BITS']:
            return False
    return True


def allowed_content(event, commands=False, **kwargs):
    message = event.message if hasattr(event, "message") else ""
    if not commands:
        if message.startswith('!'):
            logger.debug("COMMAND %s (Ignored)", message)
            return False
    if "chat" not in kwargs:
        if event.type == 'TWITCHCHATMESSAGE':
            return False
    if "alert" not in kwargs:
        # RAID, HOST, SUBGIFT, SUB
        if event.type in ['TWITCHATUSERNOTICE', 'SUB', "RAID", "HOSTED"]:
            return False
    return True


def pubsub_filter(event):
    if hasattr(event, "extra"):
        ext = event.extra

        if "pubsub" in ext:
            if hasattr(event, "type"):
                if event.type in ["SUB", "RAID", "HOSTED"]:
                    return True
    return False


class SocketServer():

    def __init__(self):
        self.channels = {}
        self.chatbot = None
        self.users = None
        self.http_clients = {}
        self.pubsub_clients = {}
        self.alert_clients = {}
        self.loop = None
        self.reload_event = None
        self.shutdown_event = None
        self.websocket_server = None
        self._event_queue = None
        self.recent_events = deque([], 20)
        self.replay_queue = Queue()

    async def broadcast(self, msg):
        for c in self.channels:
            for s in self.channels[c]:
                await s["socket"].send(json.dumps(msg))

    async def handle_content(self, channel, content):
        if "tags" in content:
            if "bits" in content["tags"]:
                bits_evt = get_bits(content)
                self.recent_events.append(bits_evt)
            if any([s.get("images", None) for s in self.channels[channel]]):
                if self.users and 'user-id' in content['tags']:
                    content['logo'] = await self.users.get_picture(content['tags']['user-id'])
            if 'response' in content['tags']:
                self.chatbot.send_message(content['message'], channel)
                content["message"] = await render_own_emotes(content["message"], self.chatbot.emotesets)
                content["badges"] = await render_badges(channel, self.chatbot.badges)

    def ban_bot(self, channel):
        logger.warning("Account has been banned from this channel")
        if not db.exists("banned"):
            db.create("banned", primary=["name"])
        db.update("banned", {"name": channel}, ["name"])
        self.chatbot.unsubscribe(channel)

    def filter_closed_connections(self, channel):
        self.channels[channel] = [s for s in self.channels[channel] if not s["socket"].closed]

    async def handle_chatbot(self, event):
        channel = event.channel
        if any(["chatbot" in c and c["chatbot"] for c in self.channels[channel]]):
            # TODO: this is a hack, when should we initialise this? add a watcher?
            # also split rendering with populating OWN_EMOTES
            if not OWN_EMOTES:
                await render_own_emotes("", self.chatbot.emotesets)

            cid = self.channels[channel][0]["channel_id"]
            if cid:
                await self.chatter.handle_message(event, cid)

    async def chat(self):
        self.chatter = ChatChatter(self.add_chat)

        # self.make_task(self.chatter.timer(), name="chatty")

        queue = self.chatbot.chat()
        processing = False
        while not self.shutdown_event.is_set():
            try:
                event = await queue.get()
                if event is None:
                    return
                processing = True
                content = await handle_message(event)
                channel = event.channel

                if not content:
                    continue

                if not channel:
                    await self.broadcast(content)
                    continue

                if channel not in self.channels:
                    logger.error(f"Message for channel '{channel}' but no socket")
                    self.chatbot.unsubscribe(channel)
                    continue

                update_event_metrics(event)

                if 'response' not in content['tags']:
                    # This message didn't come from us - maybe respond to it
                    METRIC_MESSAGES.labels(channel).inc()
                    await self.handle_chatbot(event)

                if any([allowed_content(event, **s) for s in self.channels[channel]]):
                    if event.type != 'TWITCHCHATMESSAGE':
                        self.recent_events.append(content)
                    await self.handle_content(channel, content)

                    self.filter_closed_connections(channel)
                    if channel in self.pubsub_clients:
                        if pubsub_filter(event):
                            continue  # Discard pubsub duplicated messages
                    for s in self.channels[channel]:
                        if filter_output(content, **s):
                            await s["socket"].send(json.dumps(content))

            except websockets.exceptions.ConnectionClosed as e:
                logger.info(f"ws Connection closed {e.code}")
                self.filter_closed_connections(channel)
                for s in self.channels[channel]:
                    logging.debug(f"    {s.status}")

            except BannedException as e:
                self.ban_bot(e.channel)

            except Exception as e:
                print(e)
                print(f"Error handling message: '{event}'")
                import traceback
                traceback.print_exc()

            finally:
                if processing:
                    processing = False
                    queue.task_done()

    async def replay(self):
        while not self.shutdown_event.is_set():
            try:
                obj = self.replay_queue.get_nowait()
                event = event_from_output(obj)
                event.id = str(uuid.uuid4())  # Reset the id
                if event.type in ['TWITCHCHATMESSAGE', 'BITS']:
                    channel = event.channel
                    output = await handle_message(event)
                    for s in self.channels[channel]:
                        await s["socket"].send(json.dumps(output))
                else:
                    await self._event_queue.put(event)
            except Empty:
                await asyncio.sleep(1)

    async def config_listener(self):
        while not self.shutdown_event.is_set():
            await self.reload_event.wait()
            if self.shutdown_event.is_set():
                return
            logger.info("Reloading config")
            self.load_clients()
            self.reload_event.clear()

    async def shutdown_listener(self):
        await self.shutdown_event.wait()
        self.reload_event.set()
        logger.info("Shutdown Started")
        await self.shutdown()

    async def disconnect_listener(self, ws, channel_client):
        await ws.wait_closed()
        channel = channel_client["channel"]
        logger.info("ws client disconnected")
        if "alert" in channel_client:
            if hasattr(channel_client["alert"], "cancel"):
                task = channel_client["alert"]
                task.count -= 1
                if task.count < 1:
                    task.cancel()
                    if channel in self.alert_clients:  # BUG: this should always be true
                        del self.alert_clients[channel]
                channel_client["alert"].cancel()
        if "pubsub" in channel_client:
            c = channel_client["channel"]
            if c in self.pubsub_clients:
                last = await self.pubsub_clients[c].disconnect()
                if last:
                    del self.pubsub_clients[c]

        # Sleep in case we're just refreshing
        await asyncio.sleep(2)

        self.channels[channel] = [s for s in self.channels[channel] if s["socket"].open]
        if not self.channels[channel]:
            # We're the last client, disconnect chat and clear caches
            self.chatbot.unsubscribe(channel)
            if channel in self.http_clients:
                del self.http_clients[channel]
            # TODO: cleanup API_CLIENT session
        logger.debug("ws client disconnect cleanup complete")
        self.debug_remaining_tasks()

    async def followers(self, channel):
        try:
            await asyncio.sleep(10)
            while not self.shutdown_event.is_set():
                if channel not in self.http_clients:
                    try:
                        self.http_clients[channel] = TwitchClient(self.config["client_id"], channel)
                    except Exception:
                        return
                recent_followers = await self.http_clients[channel].get_new_followers()
                if not recent_followers:
                    await asyncio.sleep(80 + randrange(20))
                    continue

                for nickname in recent_followers:
                    follower = create_follower(nickname=nickname, channel=channel)
                    await self.add_alert(follower)

                # Don't spam api
                await asyncio.sleep(80 + randrange(20))
        except CancelledError:
            pass

    async def add_alert(self, evt):
        self.recent_events.append(evt)
        await self._event_queue.put(evt)

    async def add_chat(self, evt):
        # this is threadsafe as we own the queue
        await self.chatbot.chat().put(evt)

    async def alerts(self):
        while not self.shutdown_event.is_set():
            try:
                event = await self._event_queue.get()
                if event is None:
                    logger.info("No more alerts")
                    return
                channel = event.channel

                if not channel:
                    output = OutputMessage.from_event(event)
                    await self.broadcast(output)
                    continue

                self.channels[channel] = [s for s in self.channels[channel] if not s["socket"].closed]
                if channel in self.pubsub_clients:
                    if pubsub_filter(event):
                        continue  # Discard pubsub duplicated messages

                output = OutputMessage.from_event(event)

                for s in self.channels[channel]:
                    await s["socket"].send(json.dumps(output))
            except Exception as e:
                logger.error(e)
                import traceback
                traceback.print_exc()
            finally:
                self._event_queue.task_done()

            await asyncio.sleep(1)

    @track_inprogress(METRIC_CLIENTS)
    async def handle_connect(self, ws_in, path):
        try:
            command = await ws_in.recv()
        except (websockets.ConnectionClosed, RuntimeError):
            return
        if self.shutdown_event.is_set():
            return
        logger.debug(command)

        commands = json.loads(command)

        if "channel" not in commands or "for" not in commands:
            logger.error("Invalid socket commands received")
            return

        tasks = []
        channel = ""
        channel_client = {
            "channel": commands["channel"],
            "socket": ws_in,
            "clientId": ctx_client_id.get(str(uuid.uuid4()))
        }
        channel_client.update(commands)

        channel = commands["channel"]
        if channel not in self.http_clients:
            self.http_clients[channel] = TwitchClient(self.config["client_id"], channel)

        try:
            channel_id = await self.http_clients[channel].get_channel_id(channel)
        except Exception as e:
            logger.error("Failed to retrieve channel_id: %s", e)
            channel_id = ""

        channel_client["channel_id"] = channel_id

        if "chat" in commands:
            if db.exists("banned") and db.find("banned", name=channel):
                logger.error(f"We are banned from {channel}")
                resp = {"type": "BANNED", "channel": channel}
                await ws_in.send(json.dumps(resp))
                return
            self.chatbot.subscribe(channel)
        if "auth" in commands and channel_id:
            try:
                if channel in self.pubsub_clients:
                    pubsub = self.pubsub_clients[channel]
                    channel_client["pubsub"] = pubsub
                    await pubsub.connect()
                else:
                    token = commands["auth"]
                    pubsub = PubSubClient(channel, channel_id, token, self.add_alert)
                    self.pubsub_clients[channel] = pubsub
                    channel_client["pubsub"] = pubsub
                    ps_conn = await pubsub.connect()
                    tasks.append(self.make_task(pubsub.heartbeat(ps_conn), name=f"{channel}_ps_hb"))
                    tasks.append(self.make_task(pubsub.receive_message(ps_conn),
                                                name=f"{channel}_ps_receive"))

            except ValueError:
                pass

        if "alert" in commands:
            if channel in self.alert_clients:
                self.alert_clients[channel].count += 1
            else:
                alert_task = self.make_task(self.followers(channel), name=f"{channel}_followers")
                alert_task.count = 1
                channel_client["alert"] = alert_task
                self.alert_clients[channel] = alert_task
                tasks.append(alert_task)
                self.chatbot.subscribe(channel)

        channel_client["channel"] = channel
        if channel in self.channels:
            self.channels[channel].append(channel_client)
        else:
            self.channels[channel] = [channel_client]

        tasks.append(self.make_task(
            self.disconnect_listener(ws_in, channel_client), name=f"{channel}_dc_hdlr"))

        logger.info(f"Socket client join: {commands['channel']} \"{commands['for']}\"")
        logger.debug(f"Socket client options: {command}")
        await asyncio.gather(*tasks)
        logger.info(f"Socket client leave: {commands['channel']} \"{commands['for']}\"")
        logger.debug(f"Socket client options: {command}")
        await ws_in.close()
        await asyncio.sleep(2.0)
        logger.debug("Socket Cleanup complete")

    def stop(self, *args):
        self.shutdown_event.set()

    async def shutdown(self):
        logger.info("Shutting down server")
        self.websocket_server.close()
        if self.chatbot:
            self.chatbot.close()
            queue = self.chatbot.chat()
            await queue.put(None)
        await self._event_queue.put(None)
        await asyncio.sleep(2)
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

    def debug_remaining_tasks(self):
        remaining_tasks = [task for task in asyncio.all_tasks(self.loop) if not task.done()]
        if len(remaining_tasks):
            logger.warning("%d Remaining Tasks", len(remaining_tasks))
            for t in remaining_tasks:
                logger.debug("               : %s", t)
        else:
            logger.info("No remaining tasks")

    def run(self):
        logger.info("Starting socket server")
        self.loop = asyncio.new_event_loop()
        self.loop.set_default_executor(ThreadPoolExecutor(max_workers=5))
        self._event_queue = asyncio.Queue()
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
            try:
                self.chatbot = ChatBot(self.loop, user, oauth)
            except RuntimeError:
                logger.warning("Bad config user/oauth - Chat unavailable")
        else:
            logger.warning("No config user/oauth - Chat unavailable")

        if client_id:
            try:
                self.users = Users(TwitchClient(None, None))
            except ValueError:
                logger.warning("No config client secret - API unavilable")
        else:
            logger.warning("No config client ID - API unavilable")

        self.reload_event = asyncio.Event()
        self.shutdown_event = asyncio.Event()
        self.make_task(self.chat(), name="chat")
        self.make_task(self.alerts(), name="alert")
        self.make_task(self.config_listener(), name="config")
        self.make_task(self.shutdown_listener(), name="shutdown")
        self.make_task(self.replay(), name="event_replay")

        self.webserver = WebServer(reload_evt=self.reload_event, loop=self.loop,
                                   shutdown_evt=self.shutdown_event, client_id=client_id, secret=secret,
                                   events=self.recent_events, replay=self.replay_queue)
        self.loop.run_until_complete(self.webserver.start())

        logger.info("----- AshnasBot ready! -----")

        self.loop.run_forever()

        logger.info("----- AshnasBot shutting down! -----")

        self.websocket_server.close()

        tasks = []
        tasks.append(self.make_task(self.webserver.stop(), "shutdown_web"))
        tasks.append(self.make_task(self.websocket_server.wait_closed(), "shutdown_ws"))
        tasks.append(self.make_task(cleanup(), "shutdown_api"))

        self.loop.run_until_complete(asyncio.gather(*tasks))
        self.debug_remaining_tasks()

        logger.info("Ashnasbot shutdown complete - exiting")
