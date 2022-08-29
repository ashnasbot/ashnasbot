import asyncio
import json
import logging
from random import random
from threading import Event
import uuid
import websockets
import websockets.client

from ..config import Config

MSG_PING = {"type": "PING"}
logger = logging.getLogger(__name__)

PUBSUB_MESSAGE_TYPES = [
    "SUB",
    # "RAID",
    # "HOSTED",
    # "FOLLOW",
    "REDEMPTION",
]


class PubSubClient():

    def __init__(self, channel, channel_id, token, add_event):
        self.config = Config()
        self.add_event = add_event
        self.topics = [t[0].format(channel_id=channel_id) for t in TOPICS.values()]
        self.channel = channel
        self.auth_token = token
        self.stop_event = Event()
        self.connection = None

        self.refcount = 0

    async def connect(self):
        """Connect to webSocket server.

        websockets.client.connect returns a WebSocketClientProtocol,
        which is used to send and receive messages.
        """
        self.refcount += 1
        if self.connection:
            return self.connection

        self.connection = await websockets.client.connect('wss://pubsub-edge.twitch.tv')
        if self.connection.open:
            logger.info("Connected to pubsub")
            message = {"type": "LISTEN", "nonce": str(self.generate_nonce()),
                       "data": {"topics": self.topics, "auth_token": self.auth_token}}
            logger.info(message)
            json_message = json.dumps(message)
            await self.send_message(json_message)
            return self.connection

    async def disconnect(self):
        self.refcount -= 1
        logger.debug(f"decrementing pubsub {self.refcount}")
        if self.refcount < 1:
            message = {"type": "UNLISTEN", "nonce": str(self.generate_nonce()),
                       "data": {"topics": self.topics, "auth_token": self.auth_token}}
            logger.info(message)
            logger.info("Disconnected from pubsub")
            json_message = json.dumps(message)
            await self.send_message(json_message)
            self.stop_event.set()
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
        while not self.stop_event.is_set():
            try:
                message = await connection.recv()
                evt = handle_pubsub(message)
                if evt:
                    evt["channel"] = self.channel
                    await self.add_event(evt)
            except websockets.exceptions.ConnectionClosed:
                logging.warning('Connection with pubsub server closed')
                break
            except Exception as e:
                logging.error("Pubsub failure: %s", e)

    async def heartbeat(self, connection):
        """Send heartbeat to server every minute."""
        while not self.stop_event.is_set():
            try:
                data_set = {"type": "PING"}
                json_request = json.dumps(data_set)
                await connection.send(json_request)
                await asyncio.sleep(60 + random())
            except websockets.exceptions.ConnectionClosed:
                logging.error('Connection with pubsub server closed')
                evt = make_message("SYSTEM", "PubSub Disconnected")
                evt["channel"] = self.channel
                await self.add_event(evt)
                break


def handle_pubsub(message):
    event = json.loads(message)
    evt_type = event["type"]

    if evt_type == "PONG":
        return

    # TODO: SUBs
    logger.debug(event)

    if evt_type == "MESSAGE":
        data = event["data"]
        inner_msg = json.loads(data["message"])
        topic = data["topic"].rsplit(".", 1)[0]
        res = None

        if topic in TOPIC_HANDLERS:
            handler_func = TOPIC_HANDLERS[topic]
            res = handler_func(inner_msg)
        else:
            logger.warning(f"Received PubSub message for unsuppoerted PubSub topic: {topic}")

        # if event_type == "raiding":
        #     nickname = message["raider"]["display_name"]
        #     viewers = int(message["raiding_viewer_count"])
        #     msg_type = "RAID"
        #     tags = {
        #         "display-name": nickname,
        #         "msg-id": "raid",
        #         "msg-param-viewerCount": viewers,
        #         "system-msg": f"{nickname} is raiding with a party of {viewers}",
        #     }
        #     extra.append("quoted")
        # elif event_type == "host_start":
        #     nickname = message["host"]["display_name"]
        #     viewers = int(message["hosting_viewer_count"])
        #     msg_type = "HOSTED"
        #     tags = {
        #         "display-name": nickname,
        #         "msg-id": "host",
        #         "msg-param-viewerCount": "viewers",
        #         "system-msg": f"{nickname} is hosting for {viewers} viewers",
        #     }
        #     extra.append("quoted")
        # elif event_type == "follow":
        #     nickname = message["follower"]["display_name"]
        #     msg_type = "FOLLOW"
        #     tags = {
        #         "display-name": nickname,
        #         "msg-id": "follow",
        #         "system-msg": f"{nickname} is following the channel",
        #     }
        #     extra.append("quoted")

        if res:
            return res

    elif evt_type == "RESPONSE" and event["error"]:
        message = event["error"]
        logging.info(f"PUBSUB: {message}")
        data = make_message("SYSTEM", message)
        return data

def handle_sub(message):
    msg_type = "SUB"
    plans = {
        "1": "Twitch Prime",
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
        "msg-id": "follow",
        "system-msg": f"{nickname} is following the channel",
    }
    orig_message = ""
    if message["sub_message"]["message"]:
        orig_message = message["sub_message"]["message"]
        tags["emotes"] = message["sub_message"]["emotes"]  # TODO: render emotes
    
    data = make_message(msg_type)
    data["nickname"] = nickname
    data["message"] = text
    if orig_message:
        data["orig_message"] = orig_message
    data["tags"] = tags
    data["extra"].append("quoted")
    logging.info(f"PUBSUB: {text}")
    return data

def handle_redemption(message):
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
    orig_message = ""
    if reward["is_user_input_required"]:
        orig_message = redemption["user_input"]
    
    data = make_message(msg_type)
    data["nickname"] = nickname
    if orig_message:
        data["orig_message"] = orig_message
    data["tags"] = tags
    data["extra"].append("quoted")

    if reward["image"]:
        data["logo"] = reward["image"]["url_2x"]

    logging.info(f"PUBSUB: {tags['system-msg']}")
    return data


def make_message(type, message=""):
    return {
        'badges': [],
        'nickname': "System",
        'message': message,
        'orig_message': "",
        'id':  str(uuid.uuid4()),
        'tags': {},
        'type': type,
        'channel': None,
        'extra': ["pubsub"]
    }

TOPICS = {
    "SUB": ("channel-subscribe-events-v1.{channel_id}", handle_sub),
    "REDEMPTION": ("channel-points-channel-v1.{channel_id}", handle_redemption)
}
TOPIC_HANDLERS = {t[0].rsplit(".", 1)[0]: t[1] for t in TOPICS.values()}