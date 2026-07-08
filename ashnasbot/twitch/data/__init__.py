import re
import time
import typing
import uuid
from enum import StrEnum


class EventType(StrEnum):
    TWITCHCHATMESSAGE = "TWITCHCHATMESSAGE"
    TWITCHATUSERNOTICE = "TWITCHATUSERNOTICE"
    BITS = "BITS"
    FOLLOW = "FOLLOW"
    SUB = "SUB"
    SUBGIFT = "SUBGIFT"
    RAID = "RAID"
    CLEARMSG = "CLEARMSG"
    CLEARCHAT = "CLEARCHAT"
    REDEMPTION = "REDEMPTION"
    POKEYSPEAK = "POKEYSPEAK"
    HOSTED = "HOSTED"
    BANNED = "BANNED"
    BOTINFO = "BOTINFO"
    SYSTEM = "SYSTEM"


class Event:
    def __init__(self, type=EventType.SYSTEM, message="", channel=None):
        self.type = type
        self.message = message
        self.channel = channel
        self.nickname = None
        self.badges = []
        self.id = str(uuid.uuid4())
        self.tags = {}
        self.extra = []


STATIC_CDN = "https://static-cdn.jtvnw.net/"

SUB_TIERS = [0, 3, 6, 9, 12, 18, 24, 30]

EMOTE_URL_TEMPLATE = STATIC_CDN + "/emoticons/v2/{{id}}/{{format}}/{{theme_mode}}/{{scale}}"

EMOTE_IMG_TEMPLATE = "<img src=\"" + STATIC_CDN + \
    """emoticons/v2/{eid}/default/dark/2.0" class="emote"
 alt="{alt}"
 title="{alt}"
/>"""

EMOTE_FULL_TEMPLATE = """<img class="emote" src="{url}"
 alt="{alt}"
 title="{alt}"
\\>"""

CHEERMOTE_URL_TEMPLATE = "<img src=\"{url}\" class=\"emote\"" + \
    """alt="{alt}"
title="{alt}"
/>"""

CHEERMOTE_TEXT_TEMPLATE = """<span class="cheertext-{color}">{text}</span> """

BADGE_URL_TEMPLATE = """<img class="badge" src="{url}"
alt="{alt}"
title="{alt}"
/>"""

CHEER_REGEX = re.compile(r"((?<=^)|(?<=\s))(?P<emotename>[a-zA-Z]+)(\d+)(?=(\s|$))", flags=re.IGNORECASE)
CLIP_REGEX = re.compile(
    r"(http(s)?://)?(clips\.twitch\.tv|www\.twitch\.tv/\w+/clip)/"
    r"(?P<slug>[-_a-zA-Z0-9]+)([?][=0-9a-zA-Z_&]*)*",
    flags=re.IGNORECASE)
TEIRED_BADGES = ['bits', 'bits-leader', 'sub-gifter', 'sub-gift-leader']

BITS_COLORS = [
    (1, 'gray'),
    (100, 'purple'),
    (1000, 'green'),
    (5000, 'blue'),
    (10000, 'red'),
]
BITS_INDICIES = [1, 100, 1000, 5000, 10000]

OUTPUT_MESSAGE_TEMPLATE = {
    'badges': [],
    'nickname': "",
    'message': "",
    'orig_message': "",
    'tags': {'badges': []},
    'type': EventType.SYSTEM,
    'channel': "",
    'extra': []
}

CHEERMOTES: typing.Dict[str, typing.Dict] = {}
CHANNEL_CHEERMOTES: typing.Dict[str, typing.Dict] = {}
BADGES: typing.Dict[str, str] = {}  # id: url
OWN_EMOTES: typing.Dict[str, typing.Tuple] = {}  # emoteName : (url, emoteset)


class OutputMessage(dict):
    def __init__(self, *args):
        data = OUTPUT_MESSAGE_TEMPLATE.copy()
        data['id'] = str(uuid.uuid4())
        data.update(*args)
        super().__init__(data)

    @classmethod
    def from_event(cls, event):
        return cls({
            "badges": event.badges,
            "nickname": event.nickname or "",
            "message": event.message,
            "orig_message": event.message,
            "id": event.id,
            "tags": event.tags,
            "type": event.type,
            "channel": event.channel or "",
        })


def create_follower(nickname, channel):
    evt = Event(EventType.FOLLOW)
    evt.channel = channel
    evt.nickname = nickname
    evt.tags = {
        'system-msg': f"{nickname} followed the channel",
        'tmi-sent-ts': str(int(time.time())) + "000",
        'display-name': nickname
    }
    return evt


def event_from_output(from_evt):
    evt = Event()
    for prop, val in from_evt.items():
        setattr(evt, prop, val)
    return evt
