import asyncio
import json
import unittest
from unittest.mock import AsyncMock, patch

import helpers  # noqa: F401 installs the fake config singleton

from websockets.protocol import State as WSState

from ashnasbot import socket_server
from ashnasbot.socket_server import Subscription, SubscriptionType
from ashnasbot.twitch.data import Event, EventType, OutputMessage


def make_socket():
    sock = AsyncMock()
    sock.state = WSState.OPEN
    return sock


def make_subscription(sock, channel="testchannel", types=SubscriptionType.CHAT,
                      commands=False, **kwargs):
    return Subscription(socket=sock, channel=channel, channel_id="123",
                        client_id="client-1", types=types, commands=commands, **kwargs)


def make_chat_event(channel="testchannel", message="hello world"):
    evt = Event(EventType.TWITCHCHATMESSAGE, message, channel)
    evt.nickname = "testUser"
    evt.tags = {"display-name": "testUser", "id": "msg-1", "user-id": "42"}
    return evt


def make_content(evt):
    return OutputMessage({
        "badges": [],
        "nickname": evt.nickname,
        "message": evt.message,
        "orig_message": evt.message,
        "id": evt.tags["id"],
        "tags": dict(evt.tags),
        "type": evt.type,
        "channel": evt.channel,
        "extra": ["quoted"],
    })


class SubscriptionTestCase(unittest.TestCase):

    def test_from_commands_parses_types(self):
        sock = make_socket()
        sub = Subscription.from_commands(
            sock, {"channel": "c", "chat": True, "alert": True, "commands": 1}, "123", "cid")
        self.assertIn(SubscriptionType.CHAT, sub.types)
        self.assertIn(SubscriptionType.ALERT, sub.types)
        self.assertTrue(sub.commands)

    def test_commands_filtered_unless_opted_in(self):
        sub = make_subscription(make_socket(), commands=False)
        evt = make_chat_event(message="!somecommand")
        self.assertFalse(sub.allows_event(evt))

        sub_cmd = make_subscription(make_socket(), commands=True)
        self.assertTrue(sub_cmd.allows_event(evt))

    def test_alert_only_subscriber_rejects_chat(self):
        sub = make_subscription(make_socket(), types=SubscriptionType.ALERT)
        self.assertFalse(sub.allows_event(make_chat_event()))
        self.assertFalse(sub.should_forward(make_content(make_chat_event())))

    def test_chat_subscriber_rejects_alerts(self):
        sub = make_subscription(make_socket(), types=SubscriptionType.CHAT)
        content = make_content(make_chat_event())
        content["type"] = EventType.SUB
        self.assertFalse(sub.should_forward(content))

    def test_authed_chat_subscriber_skips_duplicate_redemption_message(self):
        sub = make_subscription(make_socket(), types=SubscriptionType.CHAT, auth="tok")
        content = make_content(make_chat_event())
        content["tags"]["custom-reward-id"] = "reward-1"
        self.assertFalse(sub.should_forward(content))


class ChatDispatchTestCase(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        helpers.install_config()
        self.ss = socket_server.SocketServer()
        self.ss.config = helpers.install_config()
        self.ss.shutdown_event = asyncio.Event()
        self.ss._chat_queue = asyncio.Queue()
        self.sock = make_socket()
        self.sub = make_subscription(self.sock)
        self.ss.channels = {"testchannel": [self.sub]}

    async def run_chat(self, events):
        for evt in events:
            await self.ss._chat_queue.put(evt)
        await self.ss._chat_queue.put(None)
        with patch.object(socket_server, "ChatChatter") as chatter_cls:
            chatter_cls.return_value.warmup = AsyncMock()
            self.ss.loop = asyncio.get_running_loop()
            await self.ss.chat()

    async def test_chat_message_dispatched_to_subscriber(self):
        evt = make_chat_event()
        content = make_content(evt)
        with patch.object(socket_server, "handle_message",
                          AsyncMock(return_value=content)):
            await self.run_chat([evt])
        self.sock.send.assert_awaited_once_with(json.dumps(content))

    async def test_no_content_no_send(self):
        evt = make_chat_event()
        with patch.object(socket_server, "handle_message",
                          AsyncMock(return_value=None)):
            await self.run_chat([evt])
        self.sock.send.assert_not_awaited()

    async def test_unknown_channel_dropped(self):
        evt = make_chat_event(channel="otherchannel")
        content = make_content(evt)
        with patch.object(socket_server, "handle_message",
                          AsyncMock(return_value=content)):
            await self.run_chat([evt])
        self.sock.send.assert_not_awaited()

    async def test_handler_exception_does_not_kill_loop(self):
        bad = make_chat_event(message="boom")
        good = make_chat_event()
        content = make_content(good)
        handler = AsyncMock(side_effect=[RuntimeError("boom"), content])
        with patch.object(socket_server, "handle_message", handler):
            await self.run_chat([bad, good])
        self.sock.send.assert_awaited_once_with(json.dumps(content))

    async def test_closed_socket_filtered(self):
        self.sock.state = WSState.CLOSED
        self.sock.send.side_effect = AssertionError("should not send to closed socket")
        evt = make_chat_event()
        content = make_content(evt)
        with patch.object(socket_server, "handle_message",
                          AsyncMock(return_value=content)):
            await self.run_chat([evt])
        self.sock.send.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
