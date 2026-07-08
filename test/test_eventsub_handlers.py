import json
import unittest
from unittest.mock import AsyncMock

import helpers  # noqa: F401 installs the fake config singleton

import eventsub_messages
from ashnasbot.twitch.data import EventType
from ashnasbot.twitch.eventsub import EventSubClient


def make_client():
    return EventSubClient(alert_callback=AsyncMock(), chat_callback=AsyncMock())


def chat_message_payload(**overrides):
    payload = {
        "broadcaster_user_id": "123",
        "broadcaster_user_login": "testchannel",
        "broadcaster_user_name": "TestChannel",
        "chatter_user_id": "456",
        "chatter_user_name": "TestUser",
        "message_id": "msg-uuid-1",
        "message": {
            "text": "hello world",
            "fragments": [{"type": "text", "text": "hello world"}],
        },
        "badges": [{"set_id": "subscriber", "id": "3"}],
        "color": "#FF0000",
    }
    payload.update(overrides)
    return payload


class ChatMessageTestCase(unittest.TestCase):

    def setUp(self):
        self.cut = make_client()

    def test_basic_chat_message(self):
        evt = self.cut.handle_chat_message(chat_message_payload())
        self.assertEqual(evt.type, EventType.TWITCHCHATMESSAGE)
        self.assertEqual(evt.channel, "testchannel")
        self.assertEqual(evt.nickname, "TestUser")
        self.assertEqual(evt.message, "hello world")
        self.assertEqual(evt.tags["id"], "msg-uuid-1")
        self.assertEqual(evt.tags["room-id"], "123")
        self.assertEqual(evt.tags["_badges_raw"], [{"set_id": "subscriber", "id": "3"}])

    def test_cheer_sets_bits_tag(self):
        evt = self.cut.handle_chat_message(chat_message_payload(cheer={"bits": 500}))
        self.assertEqual(evt.tags["bits"], 500)

    def test_reply_tags(self):
        reply = {
            "parent_message_id": "parent-1",
            "parent_user_login": "someone",
            "parent_user_name": "Someone",
            "parent_message_body": "original",
        }
        evt = self.cut.handle_chat_message(chat_message_payload(reply=reply))
        self.assertEqual(evt.tags["reply-parent-msg-id"], "parent-1")
        self.assertEqual(evt.tags["reply-parent-display-name"], "Someone")

    def test_custom_reward_id(self):
        evt = self.cut.handle_chat_message(
            chat_message_payload(channel_points_custom_reward_id="reward-1"))
        self.assertEqual(evt.tags["custom-reward-id"], "reward-1")


class NotificationTestCase(unittest.TestCase):

    def setUp(self):
        self.cut = make_client()

    def test_resub(self):
        payload = {
            "notice_type": "resub",
            "broadcaster_user_login": "testchannel",
            "chatter_user_name": "TestUser",
            "resub": {"sub_tier": "1000", "cumulative_months": 12},
        }
        evt = self.cut.handle_notification(payload)
        self.assertEqual(evt.type, EventType.SUB)
        self.assertIn("12 months", evt.tags["system-msg"])
        self.assertIn("tier 1", evt.tags["system-msg"])

    def test_sub_gift(self):
        payload = {
            "notice_type": "sub_gift",
            "broadcaster_user_login": "testchannel",
            "chatter_user_name": "Gifter",
            "sub_gift": {"recipient_user_name": "Lucky"},
        }
        evt = self.cut.handle_notification(payload)
        self.assertEqual(evt.type, EventType.SUBGIFT)
        self.assertEqual(evt.nickname, "Lucky")
        self.assertEqual(evt.tags["display-name"], "Gifter")

    def test_raid(self):
        payload = {
            "notice_type": "raid",
            "broadcaster_user_login": "testchannel",
            "chatter_user_name": "Raider",
            "raid": {"user_name": "Raider", "viewer_count": 42},
        }
        evt = self.cut.handle_notification(payload)
        self.assertEqual(evt.type, EventType.RAID)
        self.assertEqual(evt.tags["msg-param-viewerCount"], 42)

    def test_unknown_notice_returns_none(self):
        payload = {"notice_type": "shiny_new_thing", "broadcaster_user_login": "c"}
        self.assertIsNone(self.cut.handle_notification(payload))


class RedemptionTestCase(unittest.TestCase):

    def test_redemption_from_fixture(self):
        payload = eventsub_messages.CUSTOM_REDEMPTION["payload"]["event"]
        cut = make_client()
        evt = cut.handle_redemption(payload)
        self.assertEqual(evt.type, EventType.REDEMPTION)
        self.assertEqual(evt.channel, "ashnas")
        self.assertEqual(evt.tags["reward-title"], "Send Jewels to Gem")
        self.assertEqual(evt.tags["cost"], 5000)
        self.assertIn("quoted", evt.extra)


class RoutingTestCase(unittest.IsolatedAsyncioTestCase):

    async def test_chat_message_routed_to_chat_callback(self):
        cut = make_client()
        message = json.dumps({
            "metadata": {"message_type": "notification"},
            "payload": {
                "subscription": {"type": "channel.chat.message"},
                "event": chat_message_payload(),
            },
        })
        await cut.handle_message(message)
        cut.chat_callback.assert_awaited_once()
        cut.alert_callback.assert_not_awaited()

    async def test_keepalive_ignored(self):
        cut = make_client()
        message = json.dumps({
            "metadata": {"message_type": "session_keepalive"},
            "payload": {},
        })
        await cut.handle_message(message)
        cut.chat_callback.assert_not_awaited()
        cut.alert_callback.assert_not_awaited()

    async def test_follow_routed_to_alert_callback(self):
        cut = make_client()
        message = json.dumps({
            "metadata": {"message_type": "notification"},
            "payload": {
                "subscription": {"type": "channel.follow"},
                "event": {"user_name": "NewFan", "broadcaster_user_login": "testchannel"},
            },
        })
        await cut.handle_message(message)
        cut.alert_callback.assert_awaited_once()
        evt = cut.alert_callback.await_args.args[0]
        self.assertEqual(evt.type, EventType.FOLLOW)
        self.assertEqual(evt.nickname, "NewFan")


if __name__ == "__main__":
    unittest.main()
