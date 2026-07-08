import unittest
from unittest.mock import AsyncMock, patch

import helpers  # noqa: F401 installs the fake config singleton

import ashnasbot.twitch as twitch


class RenderBadgesTestCase(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        # Multi-version badge sets are keyed name+version; single-version sets
        # by plain name (matches TwitchClient.get_badges_for_channel)
        self.channel_badges = {
            "subscriber12": "https://example/sub12",
            "subscriber60": "https://example/sub60",
        }
        self.global_badges = {
            "staff": "https://example/staff",
            "premium": "https://example/premium",
            "bits100": "https://example/bits100",
        }

    async def render(self, badge_str):
        with patch.object(twitch, "get_channel_badges",
                          AsyncMock(return_value=self.channel_badges)), \
             patch.object(twitch, "BADGES", self.global_badges):
            return await twitch.render_badges("testchannel", badge_str)

    async def test_versioned_badges(self):
        rendered = await self.render("subscriber/60,premium/1")
        self.assertEqual(len(rendered), 2)
        self.assertIn("https://example/sub60", rendered[0])
        self.assertIn("https://example/premium", rendered[1])

    async def test_bare_tiered_badge_does_not_crash(self):
        # Regression: a tiered badge with no /version used to hit an unbound
        # (or stale, leaked from the previous badge) 'val'
        rendered = await self.render("premium/1,bits")
        self.assertEqual(len(rendered), 1)
        self.assertIn("https://example/premium", rendered[0])

    async def test_tiered_badge_uses_own_version(self):
        rendered = await self.render("subscriber/60,bits/100")
        self.assertEqual(len(rendered), 2)
        self.assertIn("https://example/bits100", rendered[1])

    async def test_unknown_badge_skipped(self):
        rendered = await self.render("mystery/9")
        self.assertEqual(rendered, [])

    async def test_subscriber_falls_back_to_tier(self):
        # subscriber/13 badge doesn't exist; falls back to highest achieved tier (12)
        rendered = await self.render("subscriber/13")
        self.assertEqual(len(rendered), 1)
        self.assertIn("https://example/sub12", rendered[0])


class RenderBitsTestCase(unittest.IsolatedAsyncioTestCase):

    async def run_render(self, message, bits, cheermotes):
        async def fake_load(channel=None):
            pass

        def fake_get_cheermote(cheer, value):
            return cheermotes.get((cheer, value))

        with patch.object(twitch, "load_cheermotes", fake_load), \
             patch.object(twitch, "get_cheermote", fake_get_cheermote), \
             patch.object(twitch, "CHEERMOTES", {"Cheer": {}}), \
             patch.object(twitch.db, "expired", lambda tbl: False):
            return await twitch.render_bits(message, "testchannel", bits)

    async def test_known_cheermote_rendered(self):
        cheermotes = {("Cheer", 100): {"url": "https://example/cheer100"}}
        message, total = await self.run_render("Cheer150 nice", "150", cheermotes)
        self.assertIn("https://example/cheer100", message)
        self.assertEqual(total, 150)

    async def test_no_cheer_text_still_returns_tuple(self):
        # Regression: used to return a bare string, crashing the caller's unpack
        message, total = await self.run_render("no bits here", "100", {})
        self.assertEqual(message, "no bits here")
        self.assertEqual(total, 100)

    async def test_unknown_cheermote_leaves_text(self):
        # Regression: missing cheermote art used to crash with TypeError
        message, total = await self.run_render("Fancycheer500", "500", {})
        self.assertIn("Fancycheer500", message)
        self.assertEqual(total, 500)


class RenderEmotesTestCase(unittest.IsolatedAsyncioTestCase):

    async def test_positional_emote_replaced(self):
        message = await twitch.render_emotes("Kappa hello", "25:0-4")
        self.assertIn('<img src=', message)
        self.assertIn('alt="Kappa"', message)
        self.assertIn("hello", message)

    async def test_message_html_escaped(self):
        message = await twitch.render_emotes("<script> Kappa", "25:9-13")
        self.assertIn("&lt;script&gt;", message)

    async def test_no_emotes_passthrough_escapes(self):
        message = await twitch.render_emotes("a < b", None)
        self.assertEqual(message, "a &lt; b")


if __name__ == "__main__":
    unittest.main()
