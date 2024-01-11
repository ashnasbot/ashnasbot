import asyncio
import threading
import unittest
from unittest.mock import AsyncMock, MagicMock

from ashnasbot import socket_server


example = MagicMock(**{
    "channel": 'ashnasbot',
    "message": 'this is a test message',
    "nickname": 'testBot',
    "tags": {'badge-info': 'subscriber/61', 'badges': 'subscriber/60,premium/1', 'client-nonce': '7ae650d9f7564a2f3858fed289e61249', 'color': '#FBF9F9', 'display-name': 'UwUitsAWooloo', 'emotes': '', 'first-msg': '0', 'flags': '', 'id': '3e5b2b83-5930-41f7-9b52-cecab8f51c42', 'mod': '0', 'room-id': '10217631', 'subscriber': '1', 'tmi-sent-ts': '1640610293213', 'turbo': '0', 'user-id': '41065424', 'user-type': ''},
    "type": 'TWITCHCHATMESSAGE',
    "_command": 'PRIVMSG',
    "_params": '#ashnasbot :this is a test message'
})
example_serialised = """{"badges": ["<img class=\\"badge\\" src=\\"https://static-cdn.jtvnw.net/badges/v1/bbbe0db0-a598-423e-86d0-f9fb98ca1933/2\\"\\nalt=\\"premium\\"\\ntitle=\\"premium\\"\\n/>"], "nickname": "UwUitsAWooloo", "message": "this is a test message", "orig_message": "this is a test message", "id": "3e5b2b83-5930-41f7-9b52-cecab8f51c42", "tags": {"badge-info": "subscriber/61", "badges": "subscriber/60,premium/1", "client-nonce": "7ae650d9f7564a2f3858fed289e61249", "color": "#FBF9F9", "display-name": "UwUitsAWooloo", "emotes": "", "first-msg": "0", "flags": "", "id": "3e5b2b83-5930-41f7-9b52-cecab8f51c42", "mod": "0", "room-id": "10217631", "subscriber": "1", "tmi-sent-ts": "1640610293213", "turbo": "0", "user-id": "41065424", "user-type": ""}, "type": "TWITCHCHATMESSAGE", "channel": "ashnasbot", "extra": ["quoted"]}"""


class BasicTestSuite(unittest.TestCase):

    def setUp(self):
        ss = socket_server.SocketServer()
        ss.config = {}
        ss.shutdown_event = threading.Event()
        ss.chatbot = MagicMock()
        send_socket = AsyncMock()
        send_socket.closed = False
        ss.channels = {
            "ashnasbot": [{
                "socket": send_socket,
                "chat": "ashnas"
            }]
        }
        self.chat_queue = asyncio.Queue()
        ss.chatbot.chat.return_value = self.chat_queue

        self.loop = asyncio.get_event_loop()

        self.ss = ss
        self.send_socket = send_socket

    def add_chat_message(self, messages):
        setup = []

        for msg in messages:
            setup.append(self.loop.create_task(self.chat_queue.put(msg)))
        setup.append(self.loop.create_task(self.chat_queue.put(None)))
        self.loop.run_until_complete(asyncio.wait(setup))

    def test_basic_chat(self):
        self.add_chat_message([example])
        self.loop.run_until_complete(self.ss.chat())
        self.send_socket.send.assert_awaited_once_with(example_serialised)
