import aiohttp
import logging

logger = logging.getLogger(__name__)


BTTV_API_GLOBAL = "https://api.betterttv.net/3/cached/emotes/global"
BTTV_API_CHANNEL = "https://api.betterttv.net/3/cached/users/twitch/{channel}"
BTTV_EMOTE_URL_TEMPLATE = """<img src=\"https://cdn.betterttv.net/emote/{id}/2x\"
                             class="emote" alt=\"{name}\" title=\"{name}\" />"""

SESSION = None
EMOTES = {} # channel : {code : id}
REGEX = {}


async def get_emotes_for_channel(channel):
    global SESSION
    global EMOTES
    global REGEX
    if not SESSION or SESSION.closed:
        logger.info("Starting new BTTV API session")
        SESSION = aiohttp.ClientSession()

    EMOTES[channel] = {}
    REGEX[channel] = {}

    if "global" not in EMOTES:
        EMOTES["global"] = await get_global_emotes()

    url = BTTV_API_CHANNEL.format(channel=channel)

    async with SESSION.get(url) as resp:
        logger.debug("GET channel Emotes %s", url)
        emotes = await resp.json()

    if "message" in emotes and emotes["message"] == "user not found":
        if "global" not in EMOTES:
            return
    else:
        EMOTES[channel] = {
            emote["code"]: emote["id"] for emote in emotes["channelEmotes"]}
        EMOTES[channel].update(**{
            emote["code"]: emote["id"] for emote in emotes["sharedEmotes"]})

    EMOTES[channel].update(**EMOTES["global"])
    if channel not in REGEX:
        REGEX[channel] = {}
    REGEX[channel] = {k: BTTV_EMOTE_URL_TEMPLATE.format(name=k, id=v) for k, v in EMOTES[channel].items()}


async def get_global_emotes():
    global SESSION
    global EMOTES
    global REGEX
    if not SESSION or SESSION.closed:
        logger.info("Starting new BTTV API session")
        SESSION = aiohttp.ClientSession()

    async with SESSION.get(BTTV_API_GLOBAL) as resp:
        logger.debug("GET global Emotes %s", BTTV_API_GLOBAL)
        emotes = await resp.json()

    return {emote["code"]: emote["id"] for emote in emotes}


async def get_emotes(channel):
    if channel not in REGEX:
        await get_emotes_for_channel(channel)
    if channel not in REGEX:
        return None
    return REGEX[channel]


def emotes():
    return EMOTES


async def close():
    if SESSION:
        logger.info("Closing BTTV API session")
        await SESSION.close()
