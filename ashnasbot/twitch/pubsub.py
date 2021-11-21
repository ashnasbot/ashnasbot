import asyncio
from enum import Enum
import json
import logging
from threading import Event
import uuid
import websockets

from ..config import Config

MSG_PING = { "type": "PING" }
logger = logging.getLogger(__name__)

PUBSUB_MESSAGE_TYPES = [
    # "SUB",  # TODO
    "RAID",
    "HOSTED",
    "FOLLOW",
    "REDEMPTION",
]


class PubSubClient():

    def __init__(self, channel, channel_id, token, add_event):
        self.config = Config()
        self.add_event = add_event
        self.topics = [f"dashboard-activity-feed.{channel_id}"]
        self.channel = channel
        self.auth_token = token
        self.stop_event = Event()
        self.connection = None

        self.refcount = 0

    async def connect(self):
        """Connect to webSocket server.
        
        websockets.client.connect returns a WebSocketClientProtocol, which is used to send and receive messages
        """
        self.refcount += 1
        if self.connection:
            return self.connection

        self.connection = await websockets.client.connect('wss://pubsub-edge.twitch.tv')
        if self.connection.open:
            logger.info("Connected to pubsub")
            message = {"type": "LISTEN", "nonce": str(self.generate_nonce()), "data":{"topics": self.topics, "auth_token": self.auth_token}}
            logger.info(message)
            json_message = json.dumps(message)
            await self.send_message(json_message)
            return self.connection

    async def disconnect(self):
        self.refcount -= 1
        if self.refcount < 1:
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
                await asyncio.sleep(60)
            except websockets.exceptions.ConnectionClosed:
                logging.error('Connection with pubsub server closed')
                evt = make_message("SYSTEM", "PubSub Disconnected")
                evt["channel"] = self.channel
                await self.add_event(evt)
                break


def handle_pubsub(message):
    event = json.loads(message)
    evt_type = event["type"]

    logger.debug(event)
    if evt_type == "PONG":
        return

    # TODO: SUBs
    if evt_type == "MESSAGE":
        data = event["data"]
        message = json.loads(data["message"])
        msg_type = None
        tags = {}
        extra = []
        orig_message = None
        if message["type"] == "raiding":
            nickname = message["raider"]["display_name"]
            viewers = int(message["raiding_viewer_count"])
            msg_type = "RAID"
            tags = {
                "display-name": nickname,
                "msg-id": "raid",
                "msg-param-viewerCount": viewers,
                "system-msg": f"{nickname} is raiding with a party of {viewers}",
            }
            extra.append("quoted")
        elif message["type"] == "host_start":
            nickname = message["host"]["display_name"]
            viewers = int(message["hosting_viewer_count"])
            msg_type = "HOSTED"
            tags = {
                "display-name": nickname,
                "msg-id": "host",
                "msg-param-viewerCount": f"viewers",
                "system-msg": f"{nickname} is hosting for {viewers} viewers",
            }
            extra.append("quoted")
        elif message["type"] == "follow":
            nickname = message["follower"]["display_name"]
            msg_type = "FOLLOW"
            tags = {
                "display-name": nickname,
                "msg-id": "follow",
                "system-msg": f"{nickname} is following the channel",
            }
            extra.append("quoted")
        elif message["type"] == "reward-redeemed":
            nickname = message["data"]["redemption"]["user"]["display_name"]
            title = message["data"]["redemption"]["reward"]["title"]
            if "user_input" in message["data"]["redemption"]:
                orig_message = message["data"]["redemption"]["user_input"] 
            msg_type = "REDEMPTION"
            tags = {
                "cost": message["data"]["redemption"]["reward"]["cost"],
                "color": message["data"]["redemption"]["reward"]["background_color"],
                "system-msg": f"{nickname} redeemed {title}"
            }
        elif message["type"] == "channel_points_custom_reward_redemption":
            nickname = message["channel_points_redeeming_user"]["display_name"]
            title = message["channel_points_reward_title"]
            if message["channel_points_user_input"]:
                orig_message = message["channel_points_user_input"] 
            msg_type = "REDEMPTION"
            tags = {
                "system-msg": f"{nickname} redeemed {title}"
            }

        if msg_type:
            data = make_message(msg_type)
            data["nickname"] = nickname
            if orig_message:
                data["orig_message"] = orig_message
                data["message"] = orig_message
            data["tags"] = tags
            data["extra"] = extra
            return data

    #elif evt_type == "RESPONSE":
    #    message = "Connected to websocket"
    #    if event["error"]:
    #        message = event["error"]
    #    logging.info(f"PUBSUB: {message}")
    #    data = make_message("SYSTEM", message)
    #    return data

def make_message(type, message=""):
    return {
        'badges': [],
        'nickname': "System",
        'message': message,
        'orig_message': "",
        'id' :  str(uuid.uuid4()),
        'tags': {},
        'type': type,
        'channel': None,
        'extra': ["pubsub"]
    }

