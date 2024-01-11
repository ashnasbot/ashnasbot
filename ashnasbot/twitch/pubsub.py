import asyncio
import json
import logging
from random import random
import uuid
import websockets
import websockets.client

from .data import create_event
from ..config import Config

MSG_PING = {"type": "PING"}
logger = logging.getLogger(__name__)

PUBSUB_MESSAGE_TYPES = [
    "SUB",
    # "RAID",
    # "FOLLOW",
    "REDEMPTION",
]  # see handlers at end of file


class PubSubClient():

    def __init__(self, channel, channel_id, token, add_event):
        self.config = Config()
        self.add_event = add_event
        self.topics = [t[0].format(channel_id=channel_id) for t in self.TOPICS.values()]
        self.channel = channel
        self.auth_token = token
        self.stop_event = asyncio.Event()
        self.connection = None
        self.connected_event = asyncio.Event()

        self.receive_task = None
        self.heartbeat_task = None

        self.__refcount = 0

    async def connect(self) -> websockets.WebSocketClientProtocol:
        """Connect to webSocket server.

        websockets.client.connect returns a WebSocketClientProtocol,
        which is used to send and receive messages.
        """
        self.__refcount += 1
        logger.debug(f"Incrementing pubsub {self.__refcount}, self.connection {self.connection}")

        if self.connection or self.__refcount > 1:
            logger.debug(f"{self.__refcount} wait for connect")
            await self.connected_event.wait()
            logger.debug(f"{self.__refcount} connect")
            return self.connection

        self.connection = await websockets.client.connect('wss://pubsub-edge.twitch.tv')
        self.connected_event.set()
        if self.connection.open:
            logger.info("Connected to pubsub")
            message = {"type": "LISTEN", "nonce": str(self.generate_nonce()),
                       "data": {"topics": self.topics, "auth_token": self.auth_token}}
            logger.info(message)
            json_message = json.dumps(message)
            await self.send_message(json_message)
            return self.connection

    async def disconnect(self):
        self.__refcount -= 1
        logger.debug(f"Decrementing pubsub {self.__refcount}")
        if self.__refcount < 1:
            message = {"type": "UNLISTEN", "nonce": str(self.generate_nonce()),
                       "data": {"topics": self.topics, "auth_token": self.auth_token}}
            logger.info(message)
            logger.info("Disconnected from pubsub")
            json_message = json.dumps(message)
            await self.send_message(json_message)
            await asyncio.sleep(1)
            self.stop_event.set()
            await self.connection.close()
            await self.connection.wait_closed()
            return True

    @property
    def connected(self):
        return self.connection.open

    def generate_nonce(self):
        """Generate nonce from seconds since epoch (UTC)."""
        nonce = uuid.uuid1()
        oauth_nonce = nonce.hex
        return oauth_nonce

    async def send_message(self, message):
        """Send message to webSocket server"""
        await self.connection.send(message)

    async def receive_message(self, connection):
        """Receive & process server messages."""
        self.receive_task = asyncio.current_task()
        while not self.stop_event.is_set():
            try:
                message = await connection.recv()
                evt = self.handle_pubsub(message)
                if evt:
                    await self.add_event(evt)
            except websockets.exceptions.ConnectionClosed:
                logger.warning('Connection with pubsub server closed')
                break
            except Exception as e:
                logger.error("Pubsub failure: %s", e)
                import traceback
                traceback.print_exc()

    async def heartbeat(self, connection):
        """Send heartbeat to server every minute."""
        self.heartbeat_task = asyncio.current_task()
        while not self.stop_event.is_set():
            try:
                data_set = MSG_PING
                json_request = json.dumps(data_set)
                await connection.send(json_request)
                await asyncio.sleep(60 + random())
            except websockets.exceptions.ConnectionClosed:
                logger.error('Connection with pubsub server closed')
                evt = create_event("SYSTEM", "PubSub Disconnected")
                evt.channel = self.channel
                await self.add_event(evt)
                break

    def handle_pubsub(self, message):
        event = json.loads(message)
        evt_type = event["type"]

        if evt_type == "PONG":
            return

        logger.debug(event)

        if evt_type == "MESSAGE":
            data = event["data"]
            inner_msg = json.loads(data["message"])
            topic = data["topic"].rsplit(".", 1)[0]
            res = None

            if topic in self.TOPIC_HANDLERS:
                handler_func = self.TOPIC_HANDLERS[topic]
                res = handler_func(self, inner_msg)
            else:
                logger.warning(f"Received PubSub message for unsupported PubSub topic: {topic}")

            if res:
                res.channel = self.channel
                return res

        elif evt_type == "RESPONSE" and event["error"]:
            message = event["error"]
            logger.info(f"PUBSUB: {message}")
            data = create_event("SYSTEM", message)
            return data

    def handle_sub(self, message):
        msg_type = "SUB"
        plans = {
            "1": "Twitch Prime",
            "Prime": "Twitch Prime",
            "1000": "a tier 1 sub",
            "2000": "a tier 2 sub",
            "3000": "a tier 3 sub",
        }
        plan = plans[message["sub_plan"]]
        user = ""
        if "display_name" in message:
            user = message['display_name']
        else:
            user = "An anonymous gifter"

        months = "the first time"
        if "cumulative_months" in message:
            months = f"{message['cumulative_months']} months"
        elif "months" in message:
            months = f"{message['months']} months"

        if message["is_gift"]:
            nickname = message["recipient_display_name"]
            text = f"{user} just gifted {plan} to {message['recipient_display_name']}!"
        else:
            nickname = user
            text = f"{message['display_name']} just subscribed with {plan} for {months}!"
            if "streak_months" in message:
                streak_months = int(message["streak_months"])
                if streak_months > 1:
                    text += f" and is on a {streak_months} streak!"
        tags = {
            "display-name": nickname,
        }
        orig_message = ""
        if message["sub_message"]["message"]:
            orig_message = message["sub_message"]["message"]
            tags["emotes"] = message["sub_message"]["emotes"]  # TODO: render emotes

        out_msg = create_event(msg_type)
        out_msg.nickname = nickname
        out_msg.message = text
        if orig_message:
            out_msg.orig_message = orig_message
        out_msg.tags = tags
        out_msg.extra.append("quoted")
        logger.info(f"PUBSUB: {text}")
        return out_msg

    def handle_redemption(self, message):
        if message["type"] != "reward-redeemed":
            return
        content = message["data"]

        msg_type = "REDEMPTION"
        if "redemption" not in content:
            return
        redemption = content["redemption"]
        reward = redemption["reward"]

        color = reward["background_color"]
        cost = reward["cost"]
        nickname = redemption["user"]["display_name"]
        title = reward["title"]

        tags = {
            "color": color,
            "cost": cost,
            "reward-title": title,
            "system-msg": f"{nickname} redeemed {title}"
        }
        user_input = ""
        if reward["is_user_input_required"]:
            user_input = redemption["user_input"]

        out_msg = create_event("REDEMPTION", msg_type)
        out_msg.nickname = nickname
        if user_input:
            out_msg.message = user_input

        out_msg.tags = tags
        out_msg.extra.append("quoted")

        if reward["image"]:
            out_msg.logo = reward["image"]["url_2x"]

        logger.info(f"PUBSUB: {tags['system-msg']}")
        return out_msg

    TOPICS = {
        "SUB": ("channel-subscribe-events-v1.{channel_id}", handle_sub),
        "REDEMPTION": ("channel-points-channel-v1.{channel_id}", handle_redemption)
    }
    TOPIC_HANDLERS = {t[0].rsplit(".", 1)[0]: t[1] for t in TOPICS.values()}
