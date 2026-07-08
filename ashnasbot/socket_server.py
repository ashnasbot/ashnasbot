import asyncio
from collections import deque
import contextvars
from dataclasses import dataclass
from enum import Flag, auto
import json
import logging
from queue import Queue, Empty
import re
import uuid
from concurrent.futures import ThreadPoolExecutor

import websockets
import websockets.exceptions
from websockets.protocol import State as WSState
from prometheus_client import Gauge, Counter
from prometheus_async.aio import track_inprogress

from ashnasbot.twitch.eventsub import EventSubClient
from ashnasbot import llm


from .http_server import HTTPServer
from .config import Config
from .twitch import db, handle_message, get_bits, cleanup, load_own_emotes
from .twitch.chatter import ChatChatter
from .twitch.data import Event, OutputMessage, event_from_output, EventType
from .twitch.api_client import TwitchClient, ManagedToken, ChannelToken
from .twitch.commands import BannedException
from .users import Users

logger = logging.getLogger(__name__)

logging.getLogger("websockets").setLevel(logging.INFO)
ctx_client_id: contextvars.ContextVar = contextvars.ContextVar('client_id')


# Metrics
METRIC_CLIENTS = Gauge("clients", "Current client sessions")
METRIC_MESSAGES = Counter("msg_received", "Number of messages received", ["channel"])
METRIC_MESSAGES_SENT = Counter("msg_sent", "Number of messages sent", ["channel"])
METRIC_COMMANDS = Counter("commands", "Number of commands processed", ["channel"])
METRIC_SUBS = Counter("subscriptions", "Number of subscriptions received", ["channel"])
METRIC_FOLLOWS = Counter("followers", "Number of new followers received", ["channel"])
METRIC_REDEMPTION = Counter("redemptions", "Number of redemption messages received", ["channel"])
METRIC_EMOTES = Counter("emotes", "Number of emotes used in messages", ["channel"])

connect_lock = asyncio.Lock()


class SubscriptionType(Flag):
    CHAT = auto()
    ALERT = auto()


@dataclass
class Subscription:
    """Represents a single WebSocket client connection and its event subscriptions."""
    socket: object  # websockets.WebSocketServerProtocol
    channel: str
    channel_id: str
    client_id: str
    types: SubscriptionType
    commands: bool = False
    auth: str | None = None
    chatbot: bool = False
    images: bool = False

    @classmethod
    def from_commands(cls, ws, commands, channel_id, client_id):
        types = SubscriptionType(0)
        if "chat" in commands:
            types |= SubscriptionType.CHAT
        if "alert" in commands:
            types |= SubscriptionType.ALERT
        return cls(
            socket=ws,
            channel=commands["channel"],
            channel_id=channel_id,
            client_id=client_id,
            types=types,
            commands=bool(commands.get("commands", False)),
            auth=commands.get("auth"),
            chatbot=bool(commands.get("chatbot", False)),
            images=bool(commands.get("images", False)),
        )

    def allows_event(self, event) -> bool:
        """Return True if a raw Event object is eligible for processing by this subscriber.

        Filters command messages unless this subscriber opted into commands, and gates
        chat vs. alert events based on the subscriber's SubscriptionType flags.
        """
        message = event.message if hasattr(event, "message") else ""
        if not self.commands and message.startswith('!'):
            logger.debug("COMMAND %s (Ignored)", message)
            return False
        if SubscriptionType.CHAT not in self.types:
            if event.type == EventType.TWITCHCHATMESSAGE:
                return False
        if SubscriptionType.ALERT not in self.types:
            if event.type in [EventType.TWITCHATUSERNOTICE, EventType.SUB, EventType.RAID]:
                return False
        return True

    def should_forward(self, content) -> bool:
        """Return True if a serialised OutputMessage dict should be forwarded to this subscriber.

        Suppresses chat messages for alert-only subscribers, alert events for chat-only
        subscribers, and duplicate custom-reward chat messages for auth'd subscribers
        (EventSub reflects those back directly).
        """
        if SubscriptionType.CHAT not in self.types:
            if content["type"] == EventType.TWITCHCHATMESSAGE:
                return False
        elif self.auth is not None:
            # EventSub handles redemptions; suppress the duplicate IRC custom-reward message
            if "tags" in content and "custom-reward-id" in content["tags"]:
                return False
        if SubscriptionType.ALERT not in self.types:
            if content["type"] not in [EventType.TWITCHCHATMESSAGE, EventType.BITS]:
                return False
        return True


class SocketServer():

    def __init__(self):
        self.channels = {}
        self.users = None
        self.http_clients = {}
        self.loop = None
        self.reload_event = None
        self.shutdown_event = None
        self.websocket_server = None
        self._event_queue = None
        self._chat_queue = None
        self.recent_events = deque([], 20)
        self.replay_queue = Queue()
        self.event_sub = None
        self.broadcaster_event_sub = None  # separate session for broadcaster-only subs
        self._bot_token = ManagedToken("bot_token", "bot_refresh_token")
        self._channel_tokens: dict[str, ChannelToken] = {}
        self._eventsub_channels: set[str] = set()
        self._broadcaster_eventsub_channels: set[str] = set()

    @staticmethod
    def _update_event_metrics(event):
        """Increment Prometheus counters for a processed Event object."""
        c = event.channel
        match event.type:
            case EventType.SUB:
                METRIC_SUBS.labels(c).inc()
            case EventType.FOLLOW:
                METRIC_FOLLOWS.labels(c).inc()
            case EventType.REDEMPTION:
                METRIC_REDEMPTION.labels(c).inc()
        if "emotes" in event.tags and event.tags["emotes"]:
            METRIC_EMOTES.labels(c).inc(len(event.tags["emotes"].split(",")))

    async def broadcast(self, msg):
        for c in self.channels:
            for s in self.channels[c]:
                await s.socket.send(json.dumps(msg))

    async def handle_content(self, channel, content):
        if "tags" in content:
            if "bits" in content["tags"]:
                bits_evt = get_bits(content)
                self.recent_events.append(bits_evt)
            if any(s.images for s in self.channels[channel]):
                if self.users and 'user-id' in content['tags']:
                    logo = await self.users.get_picture(content['tags']['user-id'])
                    if logo:
                        content['logo'] = logo
            if 'response' in content['tags']:
                channel_id = next(
                    (c.channel_id for c in self.channels[channel] if c.channel_id), None)
                reply_to = content['tags'].get('reply-parent-msg-id')
                # Prefer dedicated bot token (validated); fall back to broadcaster token
                bot_token, bot_user_id = await self._get_valid_bot_credentials()
                if bot_token and bot_user_id:
                    send_token, sender_id = bot_token, bot_user_id
                else:
                    broadcaster_auth = next((c.auth for c in self.channels[channel] if c.auth), None)
                    send_token, sender_id = broadcaster_auth, channel_id
                if send_token and sender_id and channel_id and channel in self.http_clients:
                    await self.http_clients[channel].send_chat_message(
                        channel_id, sender_id, content['message'], send_token, reply_to)

    def ban_bot(self, channel):
        logger.warning("Account has been banned from this channel")
        db.ensure("banned", primary=["name"])
        db.update("banned", {"name": channel}, ["name"])

    def filter_closed_connections(self, channel):
        self.channels[channel] = [s for s in self.channels[channel] if s.socket.state == WSState.OPEN]

    async def handle_chatbot(self, event):
        channel = event.channel
        if any(c.chatbot for c in self.channels[channel]):
            cid = self.channels[channel][0].channel_id
            if cid:
                await self.chatter.handle_message(event, cid)

    def _event_trigger(self, event) -> str:
        """Build the LLM trigger string for a follow/sub/subgift event."""
        if event.type == EventType.FOLLOW:
            name = event.tags.get("display-name") or event.nickname or "someone"
            return f"{name} just followed!"
        return event.tags.get("system-msg") or ""

    async def _post_event_response(self, channel: str, trigger: str) -> None:
        """Generate an LLM reaction to a channel event and send it as POKEYSPEAK."""
        if not trigger or not hasattr(self, 'chatter'):
            return
        text = await asyncio.to_thread(llm.generate_event_response, trigger)
        if not text:
            return
        msg = self.chatter.make_message(channel)
        msg.message = text
        msg.tags["pokey-say"] = True
        await self.add_chat(msg)

    async def chat(self):
        self.chatter = ChatChatter(self.add_chat)
        self.make_task(self.chatter.warmup(), name="model_warmup")

        queue = self._chat_queue
        assert queue is not None
        while not self.shutdown_event.is_set():
            event = await queue.get()
            if event is None:
                return
            try:
                await self._process_chat_event(event)
            except websockets.exceptions.ConnectionClosed as e:
                logger.info(f"ws client connection closed {e.code}")
                self.filter_closed_connections(event.channel)
            except BannedException as e:
                self.ban_bot(e.channel)
            except Exception:
                logger.exception("Error handling message: '%s'", event)
            finally:
                queue.task_done()

    async def _process_chat_event(self, event):
        auth = next((c.auth for c in self.channels.get(event.channel, []) if c.auth), None)
        event.reply = self.add_chat
        content = await handle_message(event, auth)

        if not content:
            return

        channel = event.channel
        if not channel:
            await self.broadcast(content)
            return

        if channel not in self.channels:
            logger.error(f"Message for channel '{channel}' but no socket")
            return

        self._update_event_metrics(event)

        if 'response' not in content['tags']:
            if event.message.startswith('!'):
                METRIC_COMMANDS.labels(channel).inc()
            else:
                METRIC_MESSAGES.labels(channel).inc()
            await self.handle_chatbot(event)
        elif content['message'].startswith("!"):
            await self.add_chat(event_from_output(content))

        await self._dispatch_to_subscribers(event, content, channel)

        if event.tags.get("bits"):
            name = event.tags.get("display-name") or event.nickname or "someone"
            bits = event.tags["bits"]
            raw = re.sub(r'\b[A-Za-z]+\d+\b', '', event.message or "").strip()
            trigger = (f"{name} cheered {bits} bits and said: '{raw}'"
                       if raw else f"{name} cheered {bits} bits!")
            asyncio.create_task(self._post_event_response(channel, trigger))

    async def _dispatch_to_subscribers(self, event, content, channel):
        if not any(s.allows_event(event) for s in self.channels[channel]):
            return

        if event.type != EventType.TWITCHCHATMESSAGE:
            self.recent_events.append(content)
        await self.handle_content(channel, content)

        # Don't broadcast bot responses directly — EventSub reflects
        # the sent message back, which will display it exactly once.
        if 'response' in content['tags']:
            if content['tags'].get('pokey-say'):
                pokey_msg = {'type': EventType.POKEYSPEAK, 'message': content['message'], 'channel': channel}
                self.filter_closed_connections(channel)
                for s in self.channels[channel]:
                    await s.socket.send(json.dumps(pokey_msg))
            return

        self.filter_closed_connections(channel)
        for s in self.channels[channel]:
            if s.should_forward(content):
                await s.socket.send(json.dumps(content))

    async def replay(self):
        while not self.shutdown_event.is_set():
            try:
                obj = self.replay_queue.get_nowait()
            except Empty:
                await asyncio.sleep(1)
                continue
            try:
                event = event_from_output(obj)
                event.id = str(uuid.uuid4())  # Reset the id
                if event.type in [EventType.TWITCHCHATMESSAGE, EventType.BITS]:
                    channel = event.channel
                    output = await handle_message(event)
                    if output:
                        await self.handle_content(channel, output)
                    # Don't broadcast directly — EventSub reflects the message back,
                    # so this way we'll only display it exactly once.
                else:
                    await self._event_queue.put(event)
            except Exception:
                logger.exception("Failed to replay event: %s", obj)

    async def _get_valid_bot_credentials(self):
        bot_token = await self._bot_token.get()
        if not bot_token:
            return None, None
        bot_user_id = self.config.get("bot_user_id", None)
        return (bot_token, str(bot_user_id)) if bot_user_id else (None, None)

    async def _get_valid_channel_token(self, channel: str) -> str | None:
        if channel not in self._channel_tokens:
            self._channel_tokens[channel] = ChannelToken(channel)
        return await self._channel_tokens[channel].get()

    async def config_listener(self):
        while not self.shutdown_event.is_set():
            await self.reload_event.wait()
            if self.shutdown_event.is_set():
                return
            logger.info("Reloading config")
            self.load_clients()
            self._bot_token.invalidate()
            for ct in self._channel_tokens.values():
                ct.invalidate()
            self.reload_event.clear()

    async def shutdown_listener(self):
        await self.shutdown_event.wait()
        self.reload_event.set()
        logger.info("Shutdown Started")
        await self.shutdown()

    async def disconnect_listener(self, ws, sub: 'Subscription'):
        await ws.wait_closed()
        async with connect_lock:
            channel = sub.channel
            logger.info("ws client disconnected")
            # Sleep in case we're just refreshing
            await asyncio.sleep(2)

            subs = self.channels.get(channel, [])
            self.channels[channel] = [s for s in subs if s.socket.state == WSState.OPEN]
            if not self.channels[channel]:
                # Last client for this channel — drop its API client.
                # (Sessions are shared and closed at shutdown, not here.)
                self.http_clients.pop(channel, None)
            logger.debug("ws client disconnect cleanup complete")
            self.debug_remaining_tasks()

    async def add_alert(self, evt):
        self.recent_events.append(evt)
        await self._event_queue.put(evt)

    async def add_chat(self, evt):
        METRIC_MESSAGES_SENT.labels(evt.channel).inc()
        await self._chat_queue.put(evt)

    async def alerts(self):
        assert self._event_queue is not None
        while not self.shutdown_event.is_set():
            event = await self._event_queue.get()
            if event is None:
                logger.info("No more alerts")
                return
            try:
                channel = event.channel

                if not channel:
                    output = OutputMessage.from_event(event)
                    await self.broadcast(output)
                    continue

                if channel not in self.channels:
                    logger.warning("Alert for channel '%s' but no connected clients", channel)
                    continue

                self.channels[channel] = [s for s in self.channels[channel] if s.socket.state == WSState.OPEN]
                self._update_event_metrics(event)
                output = OutputMessage.from_event(event)

                for s in self.channels[channel]:
                    await s.socket.send(json.dumps(output))

                if event.type in (EventType.FOLLOW, EventType.SUB, EventType.SUBGIFT):
                    asyncio.create_task(
                        self._post_event_response(channel, self._event_trigger(event)))
            except Exception:
                logger.exception("Error handling alert: '%s'", event)
            finally:
                self._event_queue.task_done()

            await asyncio.sleep(1)

    async def _setup_eventsub(self, channel_id, bot_token, bot_user_id,
                              broadcaster_auth, tasks, channel, channel_token=None):
        """Create or update EventSub WebSocket sessions.

        Twitch requires all subscriptions on a session to come from the same
        user.  When a bot token is present, chat events go on the bot's session
        and broadcaster-only events (follow, redemptions) go on a separate
        broadcaster session.  When only a broadcaster token is available a
        single session handles everything.
        """
        # Reconnect if bot identity newly became available.
        if self.event_sub and bot_token and not self.event_sub.bot_token:
            logger.info("Bot token newly available — reconnecting EventSub with bot identity")
            await self.event_sub.close()
            self.event_sub = None
            self._eventsub_channels.clear()

        # Primary session: chat subscriptions.
        # Pass broadcaster_auth only in single-user mode (no bot token) so that
        # subscribe() can also attach broadcaster-only subs on the same session.
        chat_broadcaster = None if bot_token else broadcaster_auth
        if (bot_token or broadcaster_auth) and not self.event_sub:
            if bot_token and bot_user_id:
                await load_own_emotes(bot_user_id, bot_token)
            eventsub = EventSubClient(
                self.add_alert, self.add_chat,
                bot_token=bot_token, bot_user_id=bot_user_id)
            self.event_sub = eventsub
            await eventsub.connect()
            if channel_id not in self._eventsub_channels:
                await eventsub.subscribe(channel_id, broadcaster_token=chat_broadcaster)
                self._eventsub_channels.add(channel_id)
            tasks.append(self.make_task(eventsub.receive_message(),
                                        name=f"{channel}_es_receive"))
        elif self.event_sub:
            if bot_token:
                self.event_sub.bot_token = bot_token
            if channel_id not in self._eventsub_channels:
                await self.event_sub.subscribe(channel_id, broadcaster_token=chat_broadcaster)
                self._eventsub_channels.add(channel_id)

        # Secondary session: broadcaster-only subs (follow, redemptions).
        # Only needed when bot is active — different Twitch users must use
        # separate WebSocket sessions or Twitch returns a 400.
        # Use channel_token (stored per-channel in DB) not broadcaster_auth,
        # which may be a client-supplied token belonging to a different channel.
        if channel_token and bot_token:
            if not self.broadcaster_event_sub:
                b_eventsub = EventSubClient(self.add_alert, self.add_chat)
                self.broadcaster_event_sub = b_eventsub
                await b_eventsub.connect()
                if channel_id not in self._broadcaster_eventsub_channels:
                    await b_eventsub.subscribe_broadcaster(channel_id, channel_token)
                    self._broadcaster_eventsub_channels.add(channel_id)
                tasks.append(self.make_task(b_eventsub.receive_message(),
                                            name=f"{channel}_bc_es_receive"))
            else:
                if channel_id not in self._broadcaster_eventsub_channels:
                    await self.broadcaster_event_sub.subscribe_broadcaster(
                        channel_id, channel_token)
                    self._broadcaster_eventsub_channels.add(channel_id)

    @track_inprogress(METRIC_CLIENTS)
    async def handle_connect(self, ws_in):
        try:
            command = await ws_in.recv()
        except (websockets.ConnectionClosed, RuntimeError):
            return
        if self.shutdown_event.is_set():
            return
        logger.debug(command)

        try:
            commands = json.loads(command)
        except (json.JSONDecodeError, UnicodeDecodeError):
            logger.error("Malformed socket handshake received")
            return

        if not isinstance(commands, dict) or "channel" not in commands or "for" not in commands:
            logger.error("Invalid socket commands received")
            return

        tasks = []
        channel = commands["channel"]
        client_id = ctx_client_id.get(str(uuid.uuid4()))

        async with connect_lock:
            if channel not in self.http_clients:
                self.http_clients[channel] = TwitchClient(self.config["client_id"], channel)

            try:
                channel_id = await self.http_clients[channel].get_channel_id(channel)
            except Exception as e:
                logger.error("Failed to retrieve channel_id: %s", e)
                channel_id = ""

            if "chat" in commands:
                if db.exists("banned") and db.find("banned", name=channel):
                    logger.error(f"We are banned from {channel}")
                    resp = {"type": EventType.BANNED, "channel": channel}
                    await ws_in.send(json.dumps(resp))
                    return

            bot_token, bot_user_id = await self._get_valid_bot_credentials()
            # Prefer the server-stored channel token (auto-refreshable);
            # fall back to the token sent by the WS client for backward compat.
            channel_token = await self._get_valid_channel_token(channel)
            broadcaster_auth = channel_token or commands.get("auth")

            if channel_id:
                try:
                    await self._setup_eventsub(
                        channel_id, bot_token, bot_user_id, broadcaster_auth, tasks, channel,
                        channel_token=channel_token)
                except ValueError:
                    pass

            first_chat_connection = "chat" in commands and channel not in self.channels
            sub = Subscription.from_commands(ws_in, commands, channel_id, client_id)
            if channel in self.channels:
                self.channels[channel].append(sub)
            else:
                self.channels[channel] = [sub]

            bot_display = self.config.get("displayname", None) or self.config.get("username", None)
            if bot_display:
                await ws_in.send(json.dumps({"type": EventType.BOTINFO, "username": bot_display}))

        if first_chat_connection:
            evt = Event(EventType.TWITCHCHATMESSAGE, channel=channel)
            evt.tags["display-name"] = channel
            await self.add_alert(evt)

        tasks.append(self.make_task(
            self.disconnect_listener(ws_in, sub), name=f"{channel}_dc_hdlr"))

        log_id = client_id[-5:]

        logger.info(f"{log_id} Socket client join: {commands['channel']}"
                    f" \"{commands['for']}\"")
        logger.debug(f"{log_id} Socket client options: {command}")
        await asyncio.gather(*tasks)
        logger.info(f"{log_id} Socket client leave: {commands['channel']}"
                    f" \"{commands['for']}\"")
        logger.debug(f"{log_id} Socket client options: {command}")
        await ws_in.close()
        await asyncio.sleep(2.0)
        logger.debug(f"{log_id} Socket Cleanup complete")

    def stop(self, *args):
        self.shutdown_event.set()

    async def shutdown(self):
        logger.info("Shutting down server")
        self.stop()

        logger.debug("Closing clients")
        if self.websocket_server:
            self.websocket_server.close()

        # Explicitly close all overlay WebSocket connections so that
        # websocket_server.wait_closed() in run() doesn't block indefinitely.
        for channel_clients in self.channels.values():
            for client in channel_clients:
                if client.socket.state == WSState.OPEN:
                    await client.socket.close()
        logger.debug("Clients closed")

        # Close the EventSub WebSocket connections.
        if self.event_sub:
            await self.event_sub.close()
        if self.broadcaster_event_sub:
            await self.broadcaster_event_sub.close()

        await self._chat_queue.put(None)
        await self._event_queue.put(None)
        await asyncio.sleep(2)
        logger.info("Stopping loop")
        self.loop.stop()

    def load_clients(self):
        config = Config()
        try:
            config.reload()
        except Exception as e:
            logger.error("Failed to reload config (%s) — keeping previous values", e)
        self.config = config

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
        self._chat_queue = asyncio.Queue()
        asyncio.set_event_loop(self.loop)
        self.loop.set_debug(enabled=False)

        async def _start_ws():
            return await websockets.serve(self.handle_connect, '0.0.0.0', 8765)
        self.websocket_server = self.loop.run_until_complete(_start_ws())

        self.load_clients()
        secret = self.config.get("secret", None)
        client_id = self.config.get("client_id", None)

        if client_id:
            try:
                self.users = Users(TwitchClient(None, None))
            except ValueError:
                logger.warning("No config client secret - API unavilable")
        else:
            logger.warning("No config client ID - API unavilable")

        self.reload_event = asyncio.Event()
        self.shutdown_event = asyncio.Event()
        tasks = [
            self.make_task(self.chat(), name="chat"),
            self.make_task(self.alerts(), name="alert"),
            self.make_task(self.config_listener(), name="config"),
            self.make_task(self.shutdown_listener(), name="shutdown"),
            self.make_task(self.replay(), name="event_replay")
        ]

        self.webserver = HTTPServer(reload_evt=self.reload_event, loop=self.loop,
                                    shutdown_evt=self.shutdown_event, client_id=client_id, secret=secret,
                                    events=self.recent_events, replay=self.replay_queue)
        self.loop.run_until_complete(self.webserver.start())

        logger.info("----- AshnasBot ready! -----")

        self.loop.run_forever()

        logger.info("----- AshnasBot shutting down! -----")

        self.websocket_server.close()

        logger.debug("Cancelling global tasks")
        for t in tasks:
            t.cancel()
        logger.debug("Global tasks cancelled")

        tasks = []
        tasks.append(self.make_task(self.webserver.stop(), "shutdown_web"))
        tasks.append(self.make_task(self.websocket_server.wait_closed(), "shutdown_ws"))
        tasks.append(self.make_task(cleanup(), "shutdown_api"))

        self.loop.run_until_complete(asyncio.gather(*tasks))
        self.debug_remaining_tasks()

        logger.info("Ashnasbot shutdown complete - exiting")
