import aiohttp
import logging

logger = logging.getLogger(__name__)


BTTV_API_GLOBAL = "https://api.betterttv.net/3/cached/emotes/global"
BTTV_API_CHANNEL = "https://api.betterttv.net/3/cached/users/twitch/{channel}"
BTTV_EMOTE_URL_TEMPLATE = """<img src="https://cdn.betterttv.net/emote/{id}/2x"
class="emote" 
alt="{code}"
title="{code}"
/>"""

SESSION = None
EMOTES = {}


async def get_emotes_for_channel(channel):
    global SESSION
    if not SESSION or SESSION.closed:
        logger.info("Starting new BTTV API session")
        SESSION = aiohttp.ClientSession()

    url = BTTV_API_CHANNEL.format(channel=channel)

    async with SESSION.get(url) as resp:
        logger.debug("GET Emotes %s", url)
        emotes = await resp.json()

    if "message" in emotes and emotes["message"] == "user not found":
        EMOTES[channel] = {}
        return

    EMOTES[channel] = {
        emote["code"]: emote["id"] for emote in emotes["channelEmotes"]}

async def get_global_emotes():
    global SESSION
    if not SESSION or SESSION.closed:
        logger.info("Starting new BTTV API session")
        SESSION = aiohttp.ClientSession()

    async with SESSION.get(BTTV_API_GLOBAL) as resp:
        logger.debug("GET Emotes %s", BTTV_API_GLOBAL)
        emotes = await resp.json()

    EMOTES["global"] = {
        emote["code"]: emote["id"] for emote in emotes}

def get_emote(code, idx):
    return BTTV_EMOTE_URL_TEMPLATE.format(code=code, id=idx)

def emotes():
    return EMOTES
