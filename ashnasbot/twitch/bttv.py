import asyncio
import logging

import aiohttp

logger = logging.getLogger(__name__)


BTTV_API_GLOBAL = "https://api.betterttv.net/3/cached/emotes/global"
BTTV_API_CHANNEL = "https://api.betterttv.net/3/cached/users/twitch/{channel}"
BTTV_EMOTE_URL_TEMPLATE = """<img src=\"https://cdn.betterttv.net/emote/{id}/2x\"
                             class="emote" alt=\"{name}\" title=\"{name}\" />"""

SESSION = None
EMOTES = {}  # channel : {code : id}
REGEX = {}


def _session():
    global SESSION
    if not SESSION or SESSION.closed:
        logger.info("Starting new BTTV API session")
        SESSION = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15))
    return SESSION


async def get_emotes_for_channel(channel):
    channel_emotes = {}

    if "global" not in EMOTES:
        EMOTES["global"] = await get_global_emotes()

    url = BTTV_API_CHANNEL.format(channel=channel)

    async with _session().get(url) as resp:
        logger.debug("GET channel Emotes %s", url)
        emotes = await resp.json()

    if isinstance(emotes, dict) and "message" in emotes:
        # "user not found" etc. — fall through with global emotes only
        logger.debug("BTTV: %s for channel %s", emotes["message"], channel)
    else:
        channel_emotes = {
            emote["code"]: emote["id"] for emote in emotes.get("channelEmotes", [])}
        channel_emotes.update({
            emote["code"]: emote["id"] for emote in emotes.get("sharedEmotes", [])})

    channel_emotes.update(EMOTES["global"])
    EMOTES[channel] = channel_emotes
    REGEX[channel] = {k: BTTV_EMOTE_URL_TEMPLATE.format(name=k, id=v) for k, v in channel_emotes.items()}


async def get_global_emotes():
    async with _session().get(BTTV_API_GLOBAL) as resp:
        logger.debug("GET global Emotes %s", BTTV_API_GLOBAL)
        emotes = await resp.json()

    return {emote["code"]: emote["id"] for emote in emotes}


async def get_emotes(channel):
    """Return the channel's BTTV emote map, or None if unavailable.

    Failures are not cached — the next call retries the fetch.
    """
    if channel not in REGEX:
        try:
            await get_emotes_for_channel(channel)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as e:
            logger.warning("BTTV emote fetch failed for %s: %s", channel, e)
            return None
    return REGEX.get(channel)


def emotes():
    return EMOTES


async def close():
    if SESSION:
        logger.info("Closing BTTV API session")
        await SESSION.close()
