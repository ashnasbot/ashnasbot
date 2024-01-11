import re
import unittest

from ashnasbot.twitch.data import CLIP_REGEX


_VALID = [
    r"https://clips.twitch.tv/MollyDarlingWerewolfPeanutButterJellyTime-V6_qySbyw4qUfWks?my_ass=4&bacon=is_good",
    r"https://clips.twitch.tv/MollyDarlingWerewolfPeanutButterJellyTime-V6_qySbyw4qUfWks?my_ass=4&",
    r"https://clips.twitch.tv/VenomousQuizzicalHamsterThunBeast-1OTkJp-K1PWdEB2h",
    r"https://clips.twitch.tv/MollyDarlingWerewolfPeanutButterJellyTime-V6_qySbyw4qUfWks",
    r"clips.twitch.tv/JollyDarlingWerewolfPeanutButterJellyTime-V6_qySbyw4qUfWks",
    r"clips.twitch.tv/JollyDarlingWerewolfPeanutButterJellyTime",
    r"www.twitch.tv/example_channel/clip/VenomousQuizzicalHamsterThunBeast",
    r"https://www.twitch.tv/example_channel/clip/ShakingHonorableToffeeSquadGoals-YzRgRjVNoSjs6q0_?filter=clips&range=7d&sort=time",
]


class ClipsRegexTestCase(unittest.TestCase):

    def test_valid_clips(self):
        for url in _VALID:
            m = CLIP_REGEX.match(url)
            self.assertIsInstance(m, re.Match)
            self.assertTrue(m)
