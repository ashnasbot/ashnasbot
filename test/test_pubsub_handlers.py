import json
import unittest
from unittest.mock import MagicMock

from ashnasbot.twitch import pubsub
import pubsub_messages


class PubSubTestCase(unittest.TestCase):

    def setUp(self) -> None:
        self.cut = pubsub.PubSubClient("test", "test", "test", MagicMock)
        return super().setUp()

    def test_resub(self):
        input = prep_message(pubsub_messages.RESUB)
        res = self.cut.handle_pubsub(input)
        self.assertIsNotNone(res)
        self.assertEqual(res.type, "SUB")

    def test_giftsub(self):
        input = prep_message(pubsub_messages.SUBGIFT)
        res = self.cut.handle_pubsub(input)
        self.assertIsNotNone(res)
        self.assertEqual(res.type, "SUB")

    def test_anon_giftsub(self):
        input = prep_message(pubsub_messages.SUBGIFTANON)
        res = self.cut.handle_pubsub(input)
        self.assertIsNotNone(res)
        self.assertEqual(res.type, "SUB")

    def test_multi_month_sub(self):
        input = prep_message(pubsub_messages.SUBMULTIMONTH)
        res = self.cut.handle_pubsub(input)
        self.assertIsNotNone(res)
        self.assertEqual(res.type, "SUB")

    def test_redemption(self):
        input = prep_message(pubsub_messages.REDEMPTION)
        res = self.cut.handle_pubsub(input)
        self.assertIsNotNone(res)
        self.assertEqual(res.type, "REDEMPTION")

    def test_redemption_alt(self):
        input = prep_message(pubsub_messages.REDEMPTION2)
        res = self.cut.handle_pubsub(input)
        self.assertIsNotNone(res)
        self.assertEqual(res.type, "REDEMPTION")


class TestPubsubOutputRendering(unittest.IsolatedAsyncioTestCase):

    def setUp(self) -> None:
        self.cut = pubsub.PubSubClient("test", "test", "test", MagicMock)
        return super().setUp()

    async def test_redemption_rendering(self):
        expected_message = pubsub_messages.REDEMPTION["data"]["message"]["data"]["redemption"]["user_input"]
        expected_system_msg = pubsub_messages.REDEMPTION["data"]["message"]["data"]["redemption"]["reward"]["title"]
        from ashnasbot.twitch import handle_message
        input = prep_message(pubsub_messages.REDEMPTION)
        putbsub_out = self.cut.handle_pubsub(input)
        res = await handle_message(putbsub_out)

        self.assertIn("message", res)
        self.assertIn("tags", res)
        self.assertIn("system-msg", res["tags"])
        self.assertIn(expected_system_msg, res["tags"]["system-msg"])
        self.assertEqual(res["message"], expected_message)


def prep_message(msg):
    inner = json.dumps(msg["data"]["message"])
    msg["data"]["message"] = inner
    return json.dumps(msg)
