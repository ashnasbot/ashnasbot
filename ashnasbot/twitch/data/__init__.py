import re
import time
import uuid

from twitchobserver import Event as Message


STATIC_CDN = "https://static-cdn.jtvnw.net/"

BADGES = {
    'admin': STATIC_CDN + "chat-badges/admin-alpha.png",
    "bits1": STATIC_CDN + "/badges/v1/73b5c3fb-24f9-4a82-a852-2f475b59411c/2",
    "bits100": STATIC_CDN + "/badges/v1/09d93036-e7ce-431c-9a9e-7044297133f2/2",
    "bits1000": STATIC_CDN + "/badges/v1/0d85a29e-79ad-4c63-a285-3acd2c66f2ba/2",
    "bits10000": STATIC_CDN + "/badges/v1/68af213b-a771-4124-b6e3-9bb6d98aa732/2",
    "bits100000": STATIC_CDN + "/badges/v1/96f0540f-aa63-49e1-a8b3-259ece3bd098/2",
    "bits1000000": STATIC_CDN + "/badges/v1/494d1c8e-c3b2-4d88-8528-baff57c9bd3f/2",
    "bits1250000": STATIC_CDN + "/badges/v1/ce217209-4615-4bf8-81e3-57d06b8b9dc7/2",
    "bits1500000": STATIC_CDN + "/badges/v1/c4eba5b4-17a7-40a1-a668-bc1972c1e24d/2",
    "bits1750000": STATIC_CDN + "/badges/v1/183f1fd8-aaf4-450c-a413-e53f839f0f82/2",
    "bits200000": STATIC_CDN + "/badges/v1/4a0b90c4-e4ef-407f-84fe-36b14aebdbb6/2",
    "bits2000000": STATIC_CDN + "/badges/v1/7ea89c53-1a3b-45f9-9223-d97ae19089f2/2",
    "bits25000": STATIC_CDN + "/badges/v1/64ca5920-c663-4bd8-bfb1-751b4caea2dd/2",
    "bits2500000": STATIC_CDN + "/badges/v1/cf061daf-d571-4811-bcc2-c55c8792bc8f/2",
    "bits300000": STATIC_CDN + "/badges/v1/ac13372d-2e94-41d1-ae11-ecd677f69bb6/2",
    "bits3000000": STATIC_CDN + "/badges/v1/5671797f-5e9f-478c-a2b5-eb086c8928cf/2",
    "bits3500000": STATIC_CDN + "/badges/v1/c3d218f5-1e45-419d-9c11-033a1ae54d3a/2",
    "bits400000": STATIC_CDN + "/badges/v1/a8f393af-76e6-4aa2-9dd0-7dcc1c34f036/2",
    "bits4000000": STATIC_CDN + "/badges/v1/79fe642a-87f3-40b1-892e-a341747b6e08/2",
    "bits4500000": STATIC_CDN + "/badges/v1/736d4156-ac67-4256-a224-3e6e915436db/2",
    "bits5000": STATIC_CDN + "/badges/v1/57cd97fc-3e9e-4c6d-9d41-60147137234e/2",
    "bits50000": STATIC_CDN + "/badges/v1/62310ba7-9916-4235-9eba-40110d67f85d/2",
    "bits500000": STATIC_CDN + "/badges/v1/f6932b57-6a6e-4062-a770-dfbd9f4302e5/2",
    "bits5000000": STATIC_CDN + "/badges/v1/3f085f85-8d15-4a03-a829-17fca7bf1bc2/2",
    "bits600000": STATIC_CDN + "/badges/v1/4d908059-f91c-4aef-9acb-634434f4c32e/2",
    "bits700000": STATIC_CDN + "/badges/v1/a1d2a824-f216-4b9f-9642-3de8ed370957/2",
    "bits75000": STATIC_CDN + "/badges/v1/ce491fa4-b24f-4f3b-b6ff-44b080202792/2",
    "bits800000": STATIC_CDN + "/badges/v1/5ec2ee3e-5633-4c2a-8e77-77473fe409e6/2",
    "bits900000": STATIC_CDN + "/badges/v1/088c58c6-7c38-45ba-8f73-63ef24189b84/2",
    'bits-leader1': STATIC_CDN + "badges/v1/8bedf8c3-7a6d-4df2-b62f-791b96a5dd31/2",
    'bits-leader2': STATIC_CDN + "badges/v1/f04baac7-9141-4456-a0e7-6301bcc34138/2",
    'bits-leader3': STATIC_CDN + "badges/v1/f1d2aab6-b647-47af-965b-84909cf303aa/2",
    'broadcaster': STATIC_CDN + "chat-badges/broadcaster-alpha.png",
    'global_mod': STATIC_CDN + "badges/v1/9384c43e-4ce7-4e94-b2a1-b93656896eba/2",
    'moderator': STATIC_CDN + "chat-badges/mod-alpha.png",
    'subscriber': STATIC_CDN + "badges/v1/5d9f2208-5dd8-11e7-8513-2ff4adfae661/2",
    'sub-gifter': STATIC_CDN + "badges/v1/f1d8486f-eb2e-4553-b44f-4d614617afc1/2",
    "sub-gifter1": STATIC_CDN + "/badges/v1/f1d8486f-eb2e-4553-b44f-4d614617afc1/2",
    "sub-gifter10": STATIC_CDN + "/badges/v1/bffca343-9d7d-49b4-a1ca-90af2c6a1639/2",
    "sub-gifter100": STATIC_CDN + "/badges/v1/5056c366-7299-4b3c-a15a-a18573650bfb/2",
    "sub-gifter1000": STATIC_CDN + "/badges/v1/b8c76744-c7e9-44be-90d0-08840a8f6e39/2",
    "sub-gifter25": STATIC_CDN + "/badges/v1/17e09e26-2528-4a04-9c7f-8518348324d1/2",
    "sub-gifter250": STATIC_CDN + "/badges/v1/df25dded-df81-408e-a2d3-40d48f0d529f/2",
    "sub-gifter5": STATIC_CDN + "/badges/v1/3e638e02-b765-4070-81bd-a73d1ae34965/2",
    "sub-gifter50": STATIC_CDN + "/badges/v1/47308ed4-c979-4f3f-ad20-35a8ab76d85d/2",
    "sub-gifter500": STATIC_CDN + "/badges/v1/f440decb-7468-4bf9-8666-98ba74f6eab5/2",
    'sub-gift-leader1': STATIC_CDN + "badges/v1/21656088-7da2-4467-acd2-55220e1f45ad/2",
    'sub-gift-leader2': STATIC_CDN + "badges/v1/0d9fe96b-97b7-4215-b5f3-5328ebad271c/2",
    'sub-gift-leader3': STATIC_CDN + "badges/v1/4c6e4497-eed9-4dd3-ac64-e0599d0a63e5/2",
    'staff': STATIC_CDN + "chat-badges/staff-alpha.png",
    'turbo': STATIC_CDN + "chat-badges/turbo-alpha.png",
    'partner': STATIC_CDN + "badges/v1/d12a2e27-16f6-41d0-ab77-b780518f00a3/2",
    'premium': STATIC_CDN + "badges/v1/a1dd5073-19c3-4911-8cb4-c464a7bc1510/2",
    'vip': STATIC_CDN + "badges/v1/b817aba4-fad8-49e2-b88a-7cc744dfa6ec/2",
    'founder': STATIC_CDN + "badges/v1/511b78a9-ab37-472f-9569-457753bbe7d3/2",
    'predictions/blue-1': STATIC_CDN + 'badges/v1/e33d8b46-f63b-4e67-996d-4a7dcec0ad33/2',
    'predictions/pink-2': STATIC_CDN + 'badges/v1/4b76d5f2-91cc-4400-adf2-908a1e6cfd1e/2',
}

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
    r"(http(s)?://)?(clips\.twitch\.tv|www\.twitch\.tv/\w+/clip)/" +
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
    'id': str(uuid.uuid4()),
    'tags': {'badges': []},
    'type': "SYSTEM",
    'channel': "",
    'extra': []
}


class OutputMessage(dict):
    def __init__(self, *args):
        data = OUTPUT_MESSAGE_TEMPLATE.copy()
        data.update(*args)
        super().__init__(data)

    @classmethod
    def from_event(cls, event):
        return cls({
            "badges": event.badges if hasattr(event, "badges") else {},
            "nickname": event.nickname if hasattr(event, "nickname") else "",
            "message": event.message if hasattr(event, "message") else "",
            "orig_message": event.message if hasattr(event, "message") else "",
            "id": event.id if hasattr(event, "id") else str(uuid.uuid4()),
            "tags": event.tags if hasattr(event, "tags") else {},
            "type": event.type if hasattr(event, "type") else "SYSTEM",
            "channel": event.channel if hasattr(event, "") else "",
        })


def create_follower(nickname, channel):
    evt = Message(channel)
    evt.type = "FOLLOW"
    evt.nickname = nickname
    evt.tags = {
            'system-msg': f"{nickname} followed the channel",
            'tmi-sent-ts': str(int(time.time())) + "000",
            'display-name': nickname
        }
    return evt


def create_event(type, message=""):
    evt = Message(channel=None, command=type, message=message)
    evt.type = type  # override default type handling
    evt.nickname = None
    evt.badges = []
    evt.id = str(uuid.uuid4())
    evt.tags = {}
    evt.extra = ["pubsub"]
    return evt


def event_from_output(from_evt):
    out_evt = Message()
    for prop, val in from_evt.items():
        setattr(out_evt, prop, val)
    return out_evt
