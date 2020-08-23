import asyncio
import json
import logging
from threading import Event
import uuid
import websockets

from ..config import Config
from . import handle_redemption

MSG_PING = { "type": "PING" }
logger = logging.getLogger(__name__)


class PubSubClient():

    def __init__(self, channel_id, token, event_queue):
        self.config = Config()
        self.queue = event_queue
        self.topics = [f"channel-points-channel-v1.{channel_id}"]
        self.auth_token = token
        self.stop_event = Event()

    async def connect(self):
        """Connect to webSocket server.
        
        websockets.client.connect returns a WebSocketClientProtocol, which is used to send and receive messages
        """
        self.connection = await websockets.client.connect('wss://pubsub-edge.twitch.tv')
        if self.connection.open:
            logger.info("Connected to pubsub")
            message = {"type": "LISTEN", "nonce": str(self.generate_nonce()), "data":{"topics": self.topics, "auth_token": self.auth_token}}
            json_message = json.dumps(message)
            await self.send_message(json_message)
            return self.connection

    async def disconnect(self):
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
                evt = handle_redemption(message)
                if evt:
                    await self.queue.put(evt)
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
