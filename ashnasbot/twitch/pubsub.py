import asyncio
import json
import logging
from threading import Event
import uuid
import websockets

from ..config import Config

MSG_PING = { "type": "PING" }
logger = logging.getLogger(__name__)


class PubSubClient():

    def __init__(self, channel, channel_id, token, add_event):
        self.config = Config()
        self.add_event = add_event
        self.topics = [f"channel-points-channel-v1.{channel_id}", f"dashboard-activity-feed.{channel_id}"]
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
            return

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
                evt = handle_pubsub(self.channel, message)
                if evt:
                    evt["channel"] = self.channel
                    await self.add_event(evt)
            except websockets.exceptions.ConnectionClosed:
                logging.warning('Connection with pubsub server closed')
                break

    async def heartbeat(self, connection):
        """Send heartbeat to server every minute."""
        while not self.stop_event.is_set():
            try:
                data_set = {"type": "PING"}
                json_request = json.dumps(data_set)
                await connection.send(json_request)
                await asyncio.sleep(60)
            except websockets.exceptions.ConnectionClosed:
                logging.warning('Connection with pubsub server closed')
                break


def handle_pubsub(channel, message):
    # TODO: DRY
    event = json.loads(message)
    evt_type = event["type"]

    if evt_type == "PONG":
        return

    logger.error(event)
    if evt_type == "reward-redeemed":
        title = event["data"]["redemption"]["reward"]["title"]
        data = {
            'badges': [],
            'nickname': event["data"]["redemption"]["user"]["display_name"],
            'orig_message' : event["data"]["redemption"]["user_input"],
            'message': "",
            'id' :  uuid.uuid4(),
            'tags' : {
                "cost": event["data"]["redemption"]["reawrd"]["cost"],
                "color": event["data"]["redemption"]["reawrd"]["background_color"]
            },
            'type' : "REDEMPTION",
            'channel' : event["data"]["redemption"]["reawrd"]["channel"],
            'extra' : []
            }

        data["tags"]["system-msg"] = f"{data['nickname']} redeemed {title} for {data['tags']['cost']}"
        logging.info(f"PUBSUB: {data}")
        return data
    elif evt_type == "MESSAGE":
        data = event["data"]
        if data["type"] == "raiding":
            nickname = data["raider"]["display_name"]
            viewers = int(data["raiding_viewer_count"])
            print("PUBSUB RAID", nickname, viewers)

            return {
            "type": "RAID",
            "nickname": nickname,
            "channel": channel,
            "message": "",
            'id' :  str(uuid.uuid4()),
            "tags": {
                "display-name": nickname,
                "msg-id": "raid",
                "msg-param-viewerCount": f"viewers",
                "system-msg": f"{nickname} is raiding with a party of {viewers}",
            },
            "extra": [
                "quoted"
            ]}
        elif data["type"] == "host_start":
            nickname = data["host"]["display_name"]
            viewers = int(data["hosting_viewer_count"])
            print("PUBSUB HOST", nickname, viewers)

            return {
            "type": "HOST",
            "nickname": nickname,
            "channel": channel,
            "message": "",
            'id' :  str(uuid.uuid4()),
            "tags": {
                "display-name": nickname,
                "msg-id": "host",
                "msg-param-viewerCount": f"viewers",
                "system-msg": f"{nickname} is hosting for {viewers} viewers",
            },
            "extra": [
                "quoted"
            ]}
        elif data["type"] == "follow":
            nickname = data["follower"]["display_name"]
            print("PUBSUB FOLLOW", nickname, viewers)

            return {
            "type": "FOLLOW",
            "nickname": nickname,
            "channel": channel,
            "message": "",
            'id' :  str(uuid.uuid4()),
            "tags": {
                "display-name": nickname,
                "msg-id": "follow",
                "system-msg": f"{nickname} is following the channel",
            },
            "extra": [
                "quoted"
            ]}
    elif evt_type == "RESPONSE":
        message = "Connected to websocket"
        if event["error"]:
            message = event["error"]
        logging.info(f"PUBSUB: {message}")
        data = {
            'badges': [],
            'nickname': "System",
            'message': message,
            'orig_message': "",
            'id' :  str(uuid.uuid4()),
            'tags': {},
            'type': "SYSTEM",
            'channel': None,
            'extra': []
        }
        return data
