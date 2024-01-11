import asyncio
from enum import Enum
import json
import logging
import websockets
import websockets.client

from .data import create_follower
from .api_client import TwitchClient

logger = logging.getLogger(__name__)

SUBSCRIPTION_TYPES = {
    "channel.follow": "2",
    "channel.subscription.gift": "1",
    "channel.subscription.message": "1",
    "channel.raid": "1"
}


class MESSAGE_TYPES(str, Enum):
    KEEPALIVE = "session_keepalive"
    NOTIFY = "notification"


class EventSubClient():

    def __init__(self, user_auth_token, alert_callback):
        self.connection = None
        self.keep_alive_timeout_seconds = 10
        self.stop_event = asyncio.Event()
        self.timeout_received = asyncio.Event()
        self.session = {}
        self.api_cleint = TwitchClient(None, None)  # TODO: pass token in here?
        self.token = user_auth_token
        self.alert_callback = alert_callback

    async def connect(self):
        self.connection = await websockets.client.connect('wss://eventsub.wss.twitch.tv/ws', ping_interval=None)
        welcome_buf = await self.connection.recv()
        logger.debug(welcome_buf)
        welcome_msg = json.loads(welcome_buf)
        self.id = welcome_msg["payload"]["session"]["id"]
        self.keep_alive_timeout_seconds = welcome_msg["payload"]["session"]["keepalive_timeout_seconds"]
        self.timeout_received.set()
        return self.connection

    async def keep_alive(self, connection):
        while not self.stop_event.is_set():
            await asyncio.sleep(self.keep_alive_timeout_seconds + 1.0)
            if not self.timeout_received.is_set():
                # handle connection closed
                pass
            self.timeout_received.clear()

    async def receive_message(self, connection):
        """Receive & process server messages."""
        self.receive_task = asyncio.current_task()
        while not self.stop_event.is_set():
            try:
                message = await connection.recv()
                evt = await self.handle_message(message)
                if evt:
                    await self.alert_callback(evt)
            except Exception as e:
                logger.error("EventSub failure: %s", e)
                import traceback
                traceback.print_exc()

    async def handle_message(self, message):
        event = json.loads(message)
        msg_type = event["metadata"]["message_type"]

        if msg_type == MESSAGE_TYPES.KEEPALIVE:
            pass
        elif msg_type == MESSAGE_TYPES.NOTIFY:
            logger.debug(event)
            payload = event["payload"]["event"]
            return create_follower(payload["user_name"], payload["broadcaster_user_login"])

    async def subscribe(self, channel_id):
        # raid = to_broadcaster_user_id
        # channel points custom reward redemption
        condition = {
            "broadcaster_user_id": channel_id,
            "moderator_user_id": channel_id
        }
        await self.api_cleint.subscribe_eventsub(self.id, "channel.follow", condition=condition,
                                                 channel_id=channel_id, user_token=self.token)
