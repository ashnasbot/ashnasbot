import unittest
from unittest.mock import AsyncMock

import helpers  # noqa: F401 installs the fake config singleton

from ashnasbot.twitch import commands
from ashnasbot.twitch.data import Event, EventType
from commands._framework import PRIV


def make_command_event(message, channel="no_such_channel", badges=""):
    evt = Event(EventType.TWITCHCHATMESSAGE, message, channel)
    evt.nickname = "testUser"
    evt.tags = {
        "display-name": "testUser",
        "badges": badges,
        "id": "msg-1",
    }
    evt.reply = AsyncMock()
    return evt


class HandleCommandTestCase(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        helpers.install_config()
        # Command tables are cached per channel — keep tests independent
        commands.COMMANDS.clear()

    async def test_global_command(self):
        evt = make_command_event("!testglobal")
        res = await commands.handle_command(evt, auth=None)
        self.assertIsNotNone(res)
        self.assertIn("successful test", res["message"])

    async def test_helper_keys_stripped_from_response(self):
        evt = make_command_event("!testglobal")
        res = await commands.handle_command(evt, auth="secret-token")
        for helper_key in ("priv", "auth", "reply"):
            self.assertNotIn(helper_key, res)

    async def test_unknown_command_returns_none(self):
        evt = make_command_event("!definitelynotacommand")
        res = await commands.handle_command(evt, auth=None)
        self.assertIsNone(res)

    async def test_goaway_refused_for_common_user(self):
        evt = make_command_event("!goawayashnasbot")
        res = await commands.handle_command(evt, auth=None)
        self.assertIn("Only a mod or the broadcaster", res["message"])

    async def test_goaway_raises_banned_for_broadcaster(self):
        evt = make_command_event("!goawayashnasbot", badges="broadcaster/1")
        with self.assertRaises(commands.BannedException):
            await commands.handle_command(evt, auth=None)

    async def test_eventsub_badges_used_for_priv(self):
        evt = make_command_event("!goawayashnasbot")
        evt.tags["_badges_raw"] = [{"set_id": "moderator", "id": "1"}]
        with self.assertRaises(commands.BannedException):
            await commands.handle_command(evt, auth=None)

    async def test_common_commands_loaded_for_channel_module(self):
        # commands/ashnas.py exists and pulls in the common command set
        evt = make_command_event("!go dance", channel="ashnas")
        res = await commands.handle_command(evt, auth=None)
        self.assertIsNotNone(res)
        self.assertTrue(res["message"].startswith("Go "))

    async def test_invalid_channel_name_only_gets_globals(self):
        evt = make_command_event("!testglobal", channel="../evil")
        res = await commands.handle_command(evt, auth=None)
        self.assertIsNotNone(res)

        evt = make_command_event("!go dance", channel="../evil")
        res = await commands.handle_command(evt, auth=None)
        self.assertIsNone(res)


class PrivTestCase(unittest.TestCase):

    def test_ordering(self):
        self.assertLess(PRIV.COMMON, PRIV.SUB)
        self.assertLess(PRIV.VIP, PRIV.MOD)
        self.assertLess(PRIV.MOD, PRIV.OWNER)
        self.assertGreaterEqual(PRIV.STAFF, PRIV.OWNER)


if __name__ == "__main__":
    unittest.main()
