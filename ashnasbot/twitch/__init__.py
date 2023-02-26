import bisect
import copy
import html
from itertools import chain
import logging
import re
from uuid import uuid4
import time
import typing
import uuid

import bleach
from requests.exceptions import ConnectionError

from .api_client import TwitchClient
from ..config import Config
from .data import EMOTE_FULL_TEMPLATE, EMOTE_IMG_TEMPLATE, SUB_TIERS, BADGE_URL_TEMPLATE, BITS_COLORS
from .data import CHEERMOTE_TEXT_TEMPLATE, CHEERMOTE_URL_TEMPLATE, BITS_INDICIES, OutputMessage
from .data import TEIRED_BADGES, CHEER_REGEX, CLIP_REGEX
from . import commands
from . import db
from . import bttv

# TODO: move to data

CHEERMOTES: typing.Dict[str, typing.Dict] = {}
CHANNEL_CHEERMOTES: typing.Dict[str, typing.Dict] = {}
BADGES: typing.Dict[str, str] = {}  # id: url
OWN_EMOTES: typing.Dict[str, typing.Tuple] = {}  # emoteName : (url, emoteset)

logger = logging.getLogger(__name__)
config = Config()

API_CLIENT = None
retry = 5

while API_CLIENT is None:
    try:
        API_CLIENT = TwitchClient(None, None)
    except ValueError:
        logger.warning("No API client, API features unavailable")
        break
    except ConnectionError:
        logger.error("Failed to contact Twitch")
        retry -= 1
        if retry < 1:
            break
        time.sleep(2)


async def render_own_emotes(message, emotesets):

    if len(emotesets) > 25:
        raise ValueError("Too many subs, multiple requests needed")

    # filter to allowed emotesets
    sets = [s[1] for s in OWN_EMOTES.values()]
    missing = [s for s in emotesets if s not in sets]
    if missing:
        OWN_EMOTES.update(await API_CLIENT.get_emotes_for_sets(missing))
    emotes = {k: v for k, v in OWN_EMOTES.items() if v[1] in emotesets}

    for token in message.split():
        if token in emotes:
            message = re.sub(
                rf"\b{re.escape(token)}\b",
                EMOTE_FULL_TEMPLATE.format(url=emotes[token][0], alt=token),
                message)

    return message


async def render_emotes(message, emotes, bttv_channel=None):
    """Render emotes into message

    As a side effect, html-escapes the message
    This is unavoidable.
    """
    try:
        pattern = ""
        twitch_pattern = ""
        bttv_pattern = ""
        replacements = {}

        if emotes:

            for emote in emotes.split("/"):
                eid, pos = emote.split(':')
                occurances = pos.split(',')
                # Grab the 1st occurance, as we'll replace the rest inplace with regex.
                start, end = occurances[0].split('-')
                substr = message[int(start):int(end) + 1]
                replace_str = EMOTE_IMG_TEMPLATE.format(eid=eid, alt=substr)

                replacements[substr] = replace_str

            twitch_pattern = "|".join([re.escape(k)
                                       for k in sorted(replacements, key=len, reverse=True)])

        if bttv_channel:
            bttv_emotes = await bttv.get_emotes(bttv_channel)
            if bttv_emotes:
                bttv_pattern = "|".join([re.escape(k)
                                         for k in sorted(bttv_emotes.keys(), key=len, reverse=True)])
                replacements.update(**bttv_emotes)

        message = html.escape(message)

        pattern = "|".join(p for p in [bttv_pattern, twitch_pattern] if p)

        if pattern:
            regex = re.compile(pattern, flags=re.DOTALL)
            message = regex.sub(lambda x: replacements[x.group(0)], message)

    except Exception as e:
        logger.error(e)
        raise

    return message


async def get_channel_badges(channel):
    tbl_name = channel + "_badges"
    if not db.exists(tbl_name):
        db.create(tbl_name, primary="name")

    if not API_CLIENT:
        return {}

    if db.expired(channel + "_badges"):
        logger.info("No badge cache for %s", channel)
        badges = await API_CLIENT.get_badges_for_channel(channel)
        rows = [{"name": k, "url": v} for k, v in badges.items()]
        keys = ["name"]

        if db.exists(tbl_name):
            db.update_multi(tbl_name, rows, primary="name", keys=keys)
        else:
            db.insert_multi(tbl_name, rows, primary="name", keys=keys)

    ret = {}
    for badge in db.get(tbl_name):
        name = badge.pop('name')
        ret[name] = badge["url"]
    return ret


async def load_cheermotes(channel=None):
    global CHEERMOTES, CHANNEL_CHEERMOTES
    add_cheer = False

    if channel and channel not in CHANNEL_CHEERMOTES:
        CHANNEL_CHEERMOTES[channel] = await API_CLIENT.get_cheermotes(channel=channel)
        add_cheer = True

    if API_CLIENT and not CHEERMOTES:
        CHEERMOTES = await API_CLIENT.get_cheermotes()
        add_cheer = True

    if not db.exists("cheermotes") or db.expired("cheermotes"):
        db.create("cheermotes", ["cheer", "value"])
        add_cheer = True

    if not add_cheer:
        return

    data = []

    for p, v in chain(CHEERMOTES.items(), CHANNEL_CHEERMOTES[channel].items()):
        for i, u in v.items():
            data.append({
                "cheer": p,
                "value": i,
                "url": u
            })

    for record in data:
        db.update("cheermotes", record, ["cheer", "value"])


def get_cheermote(cheer, value):
    return db.find("cheermotes", cheer=cheer, value=value)


def get_le(collection, val):
    """Get the item in collection less than or equal to val."""
    return collection[bisect.bisect_right(collection, int(val)) - 1]


async def render_badges(channel, badges):
    global BADGES
    if not BADGES:
        BADGES = await API_CLIENT.get_global_badges()

    rendered = []
    channel_badges = await get_channel_badges(channel)
    for badgever in badges.split(','):
        if "/" in badgever:
            badge, val = badgever.split('/')
        else:
            badge = badgever
        if badge == 'subscriber':
            if not val:
                val = "0"
            # Try and grab the exact badge
            url = channel_badges.get(badge + val, None)
            if not url:
                # Otherwise grab the highest achieved sub badge
                badge = badge + str(get_le(SUB_TIERS, val))
                url = channel_badges.get(badge, None)
        elif badge in TEIRED_BADGES:
            badge = badge + val
            url = channel_badges.get(badge, None)
            if not url:
                url = BADGES.get(badge, None)
        else:
            url = channel_badges.get(badge, None)
        if not url:
            url = BADGES.get(badge, None)
            if not url:
                continue
        rendered.append(BADGE_URL_TEMPLATE.format(url=url, alt=badge))

    return rendered


async def render_bits(message, channel, bits):
    if not CHEERMOTES or db.expired("cheermotes"):
        await load_cheermotes(channel)

    total = 0

    def render_cheer(match):
        nonlocal total

        emote_name = match.group('emotename')
        real_value = match.group(3)
        if not emote_name or not real_value:
            logger.warning("Matched broken emote %s %s", emote_name, real_value)

        if emote_name == "cheer":
            emote_name = "Cheer"

        bits_value, color = BITS_COLORS[bisect.bisect_right(BITS_INDICIES, int(real_value)) - 1]
        total += int(real_value)
        cheermote = get_cheermote(emote_name, bits_value)
        if cheermote is None:
            logger.info("Channel specific cheermote not found: %s", emote_name)
            cheermote = get_cheermote("Cheer", bits_value)

        res = CHEERMOTE_URL_TEMPLATE.format(alt=emote_name, url=cheermote["url"]) + \
            CHEERMOTE_TEXT_TEMPLATE.format(color=color, text=real_value)
        return res

    match = CHEER_REGEX.search(message)
    if not match:
        logger.warn("Cannot find bits in message")
        return message

    res = CHEER_REGEX.sub(render_cheer, message)
    return res, total


async def render_clips(message):
    if not API_CLIENT:
        return message

    match = CLIP_REGEX.search(message)
    slug = match.group("slug")
    if slug is None:
        logger.error("Malformed clip url %s", match.groups())
        return message

    try:
        details = await API_CLIENT.get_clip(slug)
    except Exception:
        logger.error("Failed to get clip")
        return message

    if "data" not in details or len(details["data"]) < 1:
        logger.error("Failed to get clip")
        return message

    def render(match):
        clip = details["data"][0]
        thumbnail = clip["thumbnail_url"]
        title = clip["title"]
        clipped_by = f'Clipped by {clip["creator_name"]}'
        return f'''{match.group(0)}</br>
            <div class="inner_frame clip"><img src="{thumbnail}"/>
            <span class="title">{title}</span>
            <span class="clipper">{clipped_by}</span></div>'''
    return CLIP_REGEX.sub(render, message)


def get_bits(evt):
    evt["type"] = "BITS"
    return evt


async def handle_message(event, auth=None):
    etags = event.tags if hasattr(event, "tags") else {}
    raw_msg = event.message if hasattr(event, "message") else ""
    orig_message = raw_msg
    msg_type = event.type
    quoted = True

    extra = []

    if raw_msg.startswith('!'):
        return commands.handle_command(event, auth=auth)

    if msg_type == "RAID":
        etags['system-msg'] = f"{etags['msg-param-displayName']} is raiding with a party of " \
                              f"{etags['msg-param-viewerCount']}"

    if hasattr(event, "_command"):
        other = handle_system_commands(event)
        if other:
            return other

    if raw_msg.startswith('\u0001'):
        # Strip "\001ACTION" off /me
        raw_msg = raw_msg.replace('\u0001', "")[7:]
        orig_message = raw_msg
        quoted = False

    if 'system-msg' in etags:
        # system-messages are escaped, lets fix that
        etags['system-msg'] = html.unescape(etags['system-msg'].replace("\\s", " "))

    if quoted:
        extra.append("quoted")

    nickname = etags['display-name'] if 'display-name' in etags else ''

    badges = []
    if "badges" in etags and etags["badges"]:
        badges = await render_badges(event.channel, etags['badges'])

    temotes = 'emotes' in etags and etags["emotes"]
    bemotes = etags["room-id"] if "bttv" in config and config["bttv"] and "room-id" in etags else None
    if temotes or bemotes:
        message = await render_emotes(raw_msg, temotes, bemotes)
    else:
        # Render emotes does this as a side-effect
        message = html.escape(raw_msg)

    if re.search(CLIP_REGEX, message):
        message = await render_clips(message)

    message = bleach.linkify(message)

    if "bits" in etags:
        message, bits = await render_bits(message, event.channel, etags["bits"])
        etags["system-msg"] = f"{etags['display-name']} cheered with {bits} bits!"
        logger.info("BITS %s cheered %d", etags['display-name'], bits)

    if "id" not in etags:
        etags["id"] = str(uuid4())

    return OutputMessage({
            'badges': badges,
            'nickname': nickname,
            'message': message,
            'orig_message': orig_message,
            'id': etags['id'],
            'tags': etags,
            'type': msg_type,
            'channel': event.channel,
            'extra': extra
            })


def create_event(from_evt, message):
    new_evt = copy.copy(from_evt)
    new_evt.message = message
    return new_evt


async def cleanup():
    if API_CLIENT:
        await API_CLIENT.close()

    await bttv.close()


def handle_system_commands(event):
    try:
        if event._command == "PRIVMSG":
            # not for us
            return

        if event._command == "CLEARMSG":
            # Delete a message by id
            logger.debug("CLEAR: %s", event.tags['target-msg-id'])
            return {
                    'nickname': event.tags['login'],
                    'orig_message': event._params,
                    'id': event.tags['target-msg-id'],
                    'type': event._command
                    }
        elif event._command == "CLEARCHAT":
            # Delete all messages
            user = event.tags.get('target-user-id', "")
            logger.debug("CLEAR: %s from %s", user, event.tags['room-id'])
            return {
                    'id': str(uuid.uuid4()),
                    'user': user,
                    'room': event.tags['room-id'],
                    'type': event._command
                    }
        elif event._command == "RECONNECT":
            # IRC is going to restart
            # NOTE: We don't actually handle this yet but the notification is useful
            #       Chatbot needs to reconnect
            ret_event = OutputMessage({
                "type": "TWITCHCHATMESSAGE",
                "nickname": "Ashnasbot",
                "tags": {
                    'display-name': "Ashnasbot",
                },
                "extra": ['quoted'],
                "channel": event.channel
            })
            logger.warn("Twitch chat is going down")
            ret_event['message'] = "Twitch chat is going down"
            return ret_event

    except Exception as e:
        logger.warn(e)
        return
