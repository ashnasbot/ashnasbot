import json
import unittest

from ashnasbot.twitch import pubsub
import pubsub_messages

class PubSubestCase(unittest.TestCase):

    def test_resub(self):
        input = prep_message(pubsub_messages.RESUB)
        res = pubsub.handle_pubsub(input)
        self.assertIsNotNone(res)
        self.assertEqual(res["type"], "SUB")

    def test_giftsub(self):
        input = prep_message(pubsub_messages.SUBGIFT)
        res = pubsub.handle_pubsub(input)
        self.assertIsNotNone(res)
        self.assertEqual(res["type"], "SUB")

    def test_anon_giftsub(self):
        input = prep_message(pubsub_messages.SUBGIFTANON)
        res = pubsub.handle_pubsub(input)
        self.assertIsNotNone(res)
        self.assertEqual(res["type"], "SUB")

    def test_multi_month_sub(self):
        input = prep_message(pubsub_messages.SUBMULTIMONTH)
        res = pubsub.handle_pubsub(input)
        self.assertIsNotNone(res)
        self.assertEqual(res["type"], "SUB")

    def test_redemption(self):
        input = prep_message(pubsub_messages.REDEMPTION)
        res = pubsub.handle_pubsub(input)
        self.assertIsNotNone(res)
        self.assertEqual(res["type"], "REDEMPTION")

    def test_redemption_alt(self):
        input = prep_message(pubsub_messages.REDEMPTION2)
        res = pubsub.handle_pubsub(input)
        self.assertIsNotNone(res)
        self.assertEqual(res["type"], "REDEMPTION")

def prep_message(msg):
    inner = json.dumps(msg["data"]["message"])
    msg["data"]["message"] = inner
    return json.dumps(msg)