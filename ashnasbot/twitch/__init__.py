import bisect
import html
from itertools import chain
import logging
import re
import time
from uuid import uuid4
import uuid

import bleach

from .api_client import TwitchClient
from ..config import Config
from .data import EMOTE_FULL_TEMPLATE, EMOTE_IMG_TEMPLATE, SUB_TIERS, BADGE_URL_TEMPLATE, BITS_COLORS
from .data import CHEERMOTE_TEXT_TEMPLATE, CHEERMOTE_URL_TEMPLATE, BITS_INDICIES, OutputMessage, EventType
from .data import TEIRED_BADGES, CHEER_REGEX, CLIP_REGEX, CHEERMOTES, OWN_EMOTES, BADGES, CHANNEL_CHEERMOTES
from . import commands
from . import db
from . import bttv

logger = logging.getLogger(__name__)
config = Config()

try:
    API_CLIENT = TwitchClient(None, None)
except ValueError:
    API_CLIENT = None
    logger.warning("No API client, API features unavailable")

# In-memory badge cache: channel -> (expiry_timestamp, badges dict).
# Avoids a sqlite round-trip for every rendered message.
_BADGE_CACHE_TTL = 3600
_badge_cache: dict = {}


async def load_own_emotes(user_id, user_token):
    if OWN_EMOTES or not API_CLIENT:
        return
    emotes = await API_CLIENT.get_user_emotes(user_id, user_token)
    if emotes:
        OWN_EMOTES.update(emotes)
        logger.info("Loaded %d own emotes", len(emotes))


async def render_emotes(message, emotes, bttv_channel=None):
    """Render emotes into message

    As a side effect, html-escapes the message
    This is unavoidable.
    """
    raw_message = message
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
                # Keys must be html-escaped to match the escaped message text
                escaped_bttv = {html.escape(k): v for k, v in bttv_emotes.items()}
                bttv_pattern = "|".join([r"(?<!\S)" + re.escape(k) + r"(?!\S)"
                                         for k in sorted(escaped_bttv.keys(), key=len, reverse=True)])
                replacements.update(**escaped_bttv)

        message = html.escape(message)

        pattern = "|".join(p for p in [bttv_pattern, twitch_pattern] if p)

        if pattern:
            regex = re.compile(pattern, flags=re.DOTALL)
            message = regex.sub(lambda x: replacements[x.group(0)], message)

    except Exception:
        # Never lose a message to emote rendering — fall back to plain text
        logger.exception("Emote rendering failed")
        return html.escape(raw_message)

    return message


async def get_channel_badges(channel):
    tbl_name = channel + "_badges"

    if not API_CLIENT:
        return {}

    cached = _badge_cache.get(channel)
    if cached and cached[0] > time.time():
        return cached[1]

    if db.expired(tbl_name):
        logger.info("No badge cache for %s", channel)
        try:
            badges = await API_CLIENT.get_badges_for_channel(channel)
        except ValueError as e:
            logger.warning("Failed to fetch badges for %s: %s", channel, e)
            badges = {}
        rows = [{"name": k, "url": v} for k, v in badges.items()]

        if rows:
            db.ensure(tbl_name, primary="name")
            db.update_multi(tbl_name, rows, keys=["name"])
        else:
            db.touch(tbl_name)

    ret = {}
    if db.exists(tbl_name):
        for badge in db.get(tbl_name):
            ret[badge["name"]] = badge["url"]
    _badge_cache[channel] = (time.time() + _BADGE_CACHE_TTL, ret)
    return ret


async def load_cheermotes(channel=None):
    global CHEERMOTES

    if not API_CLIENT:
        return

    add_cheer = False

    if channel and channel not in CHANNEL_CHEERMOTES:
        try:
            CHANNEL_CHEERMOTES[channel] = await API_CLIENT.get_cheermotes(channel=channel)
        except ValueError as e:
            logger.warning("Failed to fetch cheermotes for %s: %s", channel, e)
            CHANNEL_CHEERMOTES[channel] = {}
        add_cheer = True

    if not CHEERMOTES:
        CHEERMOTES = await API_CLIENT.get_cheermotes()
        add_cheer = True

    if db.expired("cheermotes"):
        add_cheer = True
    if not db.exists("cheermotes"):
        add_cheer = True
    db.ensure("cheermotes", ["cheer", "value"])

    if not add_cheer:
        return

    data = []

    for p, v in chain(CHEERMOTES.items(), CHANNEL_CHEERMOTES.get(channel, {}).items()):
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
    if not BADGES and API_CLIENT:
        BADGES = await API_CLIENT.get_global_badges()

    rendered = []
    channel_badges = await get_channel_badges(channel)
    for badgever in badges.split(','):
        if "/" in badgever:
            badge, val = badgever.split('/', 1)
        else:
            badge, val = badgever, ""
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


async def _render_raw_badges(channel, badges_raw):
    """Render an EventSub badge array ([{"set_id":..., "id":...}]) to badge HTML."""
    global BADGES
    if not BADGES and API_CLIENT:
        BADGES = await API_CLIENT.get_global_badges()

    rendered = []
    channel_badges = await get_channel_badges(channel)
    for badge_entry in badges_raw:
        badge = badge_entry.get("set_id", "")
        val = badge_entry.get("id", "")

        if badge == "subscriber":
            url = channel_badges.get(badge + val, None)
            if not url:
                badge_key = badge + str(get_le(SUB_TIERS, val))
                url = channel_badges.get(badge_key, None)
        elif badge in TEIRED_BADGES:
            badge_key = badge + val
            url = channel_badges.get(badge_key, None)
            if not url:
                url = BADGES.get(badge_key, None)
        else:
            url = channel_badges.get(badge, None)

        if not url:
            url = BADGES.get(badge, None)
        if url:
            rendered.append(BADGE_URL_TEMPLATE.format(url=url, alt=badge))

    return rendered


async def render_eventsub_message(fragments, badges_raw, channel, bits=None, room_id=None):
    """Render an EventSub fragment list to an HTML message string plus badge list."""
    if bits and (not CHEERMOTES or db.expired("cheermotes")):
        await load_cheermotes(channel)

    bttv_emotes = {}
    if room_id and "bttv" in config and config["bttv"]:
        bttv_emotes = await bttv.get_emotes(room_id) or {}

    parts = []
    for frag in fragments:
        ftype = frag["type"]
        if ftype == "text":
            tokens = frag["text"].split(" ")
            rendered_tokens = []
            for token in tokens:
                if token in OWN_EMOTES:
                    url, _ = OWN_EMOTES[token]
                    rendered_tokens.append(EMOTE_FULL_TEMPLATE.format(url=url, alt=html.escape(token)))
                elif token in bttv_emotes:
                    rendered_tokens.append(bttv_emotes[token])
                else:
                    rendered_tokens.append(html.escape(token))
            parts.append(" ".join(rendered_tokens))
        elif ftype == "emote":
            eid = frag["emote"]["id"]
            parts.append(EMOTE_IMG_TEMPLATE.format(eid=eid, alt=html.escape(frag["text"])))
        elif ftype == "cheermote":
            cheer_data = frag["cheermote"]
            prefix = cheer_data["prefix"]
            bit_amount = cheer_data["bits"]
            bits_value, color = BITS_COLORS[bisect.bisect_right(BITS_INDICIES, bit_amount) - 1]
            cheermote = get_cheermote(prefix, bits_value)
            if cheermote is None:
                cheermote = get_cheermote("Cheer", bits_value)
            if cheermote:
                parts.append(CHEERMOTE_URL_TEMPLATE.format(alt=html.escape(prefix), url=cheermote["url"]))
                parts.append(CHEERMOTE_TEXT_TEMPLATE.format(color=color, text=bit_amount))
            else:
                parts.append(html.escape(frag["text"]))
        elif ftype == "mention":
            parts.append(html.escape(frag["text"]))
        else:
            parts.append(html.escape(frag.get("text", "")))

    message = "".join(parts)
    message = bleach.linkify(message)
    badges = await _render_raw_badges(channel, badges_raw)
    return message, badges


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
            return match.group(0)

        if emote_name == "cheer":
            emote_name = "Cheer"

        bits_value, color = BITS_COLORS[bisect.bisect_right(BITS_INDICIES, int(real_value)) - 1]
        total += int(real_value)
        cheermote = get_cheermote(emote_name, bits_value)
        if cheermote is None:
            logger.info("Channel specific cheermote not found: %s", emote_name)
            cheermote = get_cheermote("Cheer", bits_value)
        if cheermote is None:
            # No cheermote art available at all — leave the text as-is
            return match.group(0)

        res = CHEERMOTE_URL_TEMPLATE.format(alt=emote_name, url=cheermote["url"]) + \
            CHEERMOTE_TEXT_TEMPLATE.format(color=color, text=real_value)
        return res

    match = CHEER_REGEX.search(message)
    if not match:
        logger.warning("Cannot find bits in message")
        return message, int(bits) if bits else 0

    res = CHEER_REGEX.sub(render_cheer, message)
    return res, total


async def render_clips(message):
    if not API_CLIENT:
        return message

    match = CLIP_REGEX.search(message)
    if not match:
        return message
    slug = match.group("slug")
    if slug is None:
        logger.error("Malformed clip url %s", match.groups())
        return message

    try:
        details = await API_CLIENT.get_clip(slug)
    except Exception:
        logger.exception("Failed to get clip")
        return message

    if not details or not details.get("data"):
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
    evt["type"] = EventType.BITS
    return evt


async def handle_message(event, auth=None):
    etags = event.tags if hasattr(event, "tags") else {}
    raw_msg = event.message if hasattr(event, "message") else ""
    orig_message = raw_msg
    msg_type = event.type
    quoted = True

    extra = []

    if raw_msg.startswith('!'):
        return await commands.handle_command(event, auth=auth)

    if msg_type == EventType.RAID:
        etags['system-msg'] = f"{etags.get('msg-param-displayName', 'Someone')} is raiding with a party of " \
                              f"{etags.get('msg-param-viewerCount', '?')}"

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
    if "_fragments" in etags:
        # EventSub path: fragment-based rendering
        message, badges = await render_eventsub_message(
            etags["_fragments"], etags.get("_badges_raw", []), event.channel,
            bits=etags.get("bits"), room_id=etags.get("room-id"))
    else:
        # IRC path: position-based emote rendering
        if "badges" in etags and etags["badges"]:
            badges = await render_badges(event.channel, etags['badges'])

        temotes = 'emotes' in etags and etags["emotes"]
        bemotes = etags["room-id"] if "bttv" in config and config["bttv"] and "room-id" in etags else None
        if temotes or bemotes:
            message = await render_emotes(raw_msg, temotes, bemotes)
        else:
            # Render emotes does this as a side-effect
            # Responses are assumed to already be escaped
            if "response" in etags:
                message = html.unescape(raw_msg)
            else:
                message = html.escape(raw_msg)

        if re.search(CLIP_REGEX, message):
            message = await render_clips(message)

        message = bleach.linkify(message)

    if "bits" in etags:
        if "_fragments" in etags:
            # Cheermotes already rendered inline by render_eventsub_message
            bits = etags["bits"]
        else:
            message, bits = await render_bits(message, event.channel, etags["bits"])
        etags["system-msg"] = f"{nickname} cheered with {bits} bits!"
        logger.info("BITS %s cheered %s", nickname, bits)

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


async def cleanup():
    if API_CLIENT:
        await API_CLIENT.close()

    await bttv.close()
    logger.debug("ashnasbot cleanup complete")


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
                "type": EventType.TWITCHCHATMESSAGE,
                "nickname": "Ashnasbot",  # TODO: Use generic event type
                "tags": {
                    'display-name': "Ashnasbot",
                },
                "extra": ['quoted'],
                "channel": event.channel
            })
            logger.warning("Twitch chat is going down")
            ret_event['message'] = "Twitch chat is going down"
            return ret_event

    except Exception:
        logger.exception("Failed to handle system command %s", getattr(event, "_command", "?"))
        return
