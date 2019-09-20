import bisect
import copy
import html
import json
import logging
import re
import sys

import bleach
import dataset

from .api_client import TwitchClient
from .data import *
from . import commands

db = dataset.connect('sqlite:///twitchdata.db')

# TODO: Split this into: chat, emotes, badges & commands modules

logger = logging.getLogger(__name__)


def render_emotes(message, emotes):
    """Render emotes into message

    As a side effect, html-escapes the message
    This is unavoidable.
    """
    try:
        replacements = {}

        for emote in emotes.split("/"):
            eid, pos = emote.split(':')
            occurances = pos.split(',')
            # Grab the 1st occurance, as we'll replace the rest inplace with regex.
            start, end = occurances[0].split('-')
            substr = message[int(start):int(end) + 1]
            replace_str = EMOTE_URL_TEMPLATE.format(eid=eid, alt=substr)

            replacements[substr] = replace_str

        message = html.escape(message)

        pattern = re.compile("|".join([re.escape(k) for k in sorted(replacements,key=len,reverse=True)]), flags=re.DOTALL)
        message = pattern.sub(lambda x: replacements[x.group(0)], message)

    except Exception as e:
        logger.error(e)
        raise
    
    return message

async def get_channel_badges(channel):
    table = db.create_table(channel + "_badges", 
                            primary_id="name",
                            primary_type=db.types.text)
    if table:
        # TODO: Check timestamp and re-pull
        pass
    else:
        logger.info("No badge cache for %s", channel)
        client = TwitchClient(None, None)
        badges = await client.get_badges_for_channel(channel)
        rows = [{"name":k, "url":v} for k,v in badges.items()]

        table.insert_many(rows, ensure=True)

    ret = {}
    for badge in table.all():
        name = badge.pop('name')
        ret[name] = badge["url"]
    return ret

CHEERMOTES = {}
async def load_cheermotes():
    global CHEERMOTES 
    client = TwitchClient(None, None)
    CHEERMOTES = await client.get_cheermotes()

def get_cheermotes(cheer, value):
    data = []

    for p,v in CHEERMOTES.items():
        for i,u in v.items():
            data.append({
                "cheer": p,
                "value": i,
                "url": u
            })

    table = db["cheermotes"]
    table.insert_many(data)

    return table.find_one(cheer=cheer, value=value)
        
async def render_badges(channel, badges):
    channel_badges = await get_channel_badges(channel)
    rendered = []
    for badgever in badges.split(','):
        if "/" in badgever:
            badge, val = badgever.split('/')
        else:
            badge = badgever
        if badge == 'subscriber':
            if not val:
                val = "0"
            # TODO: refactor to common "get_le" method (and bits)
            badge = badge + str(SUB_TIERS[bisect.bisect_right(SUB_TIERS, int(val)) - 1])
            url = channel_badges.get(badge, None)
        elif badge == 'bits':
            badge = badge + val
            url = BADGES.get(badge, None)
        else:
            url = channel_badges.get(badge, None)
        if not url:
            url = BADGES.get(badge, None)
            if not url:
                continue
        rendered.append(BADGE_URL_TEMPLATE.format(url=url, alt=badge))

    return rendered

async def render_bits(message, bits):
    # Can't async into re method
    if not CHEERMOTES:
        await load_cheermotes()

    def render_cheer(match):
        emote_name = match.group('emotename')
        real_value = match.group(3)
        if not emote_name or not real_value:
            logger.warning("Matched broken emote %s %s", emote_name, real_value)

        if emote_name == "cheer":
            emote_name = "Cheer"

        bits_value, color = BITS_COLORS[bisect.bisect_right(BITS_INDICIES, int(real_value)) - 1]
        cheermote = get_cheermotes(emote_name, bits_value)
        if cheermote == None:
            logger.info("Channel specific emote not found: %s", emote_name)
            cheermote = get_cheermotes("Cheer", bits_value)

        res = CHEERMOTE_URL_TEMPLATE.format(alt=emote_name, url=cheermote["url"]) + \
              CHEERMOTE_TEXT_TEMPLATE.format(color=color, text=real_value)
        return res

    # TODO: compile
    cheer_regex = r"((?<=^)|(?<=\s))(?P<emotename>[a-zA-Z]+)(\d+)(?=(\s|$))"
    match = re.search(cheer_regex, message)
    if not match:
        logger.warn("Cannot find bits in message")
        return message

    return re.sub(cheer_regex, render_cheer, message, flags=re.IGNORECASE)
    


async def handle_message(event):
    etags = event.tags if hasattr(event, "tags") else {}
    raw_msg = event.message if hasattr(event, "message") else ""
    orig_message = raw_msg
    msg_type = event.type

    extra = []


    if msg_type == "RAID":
        raw_msg = f"{etags['msg-param-displayName']} is raiding with a party of " \
                  f"{etags['msg-param-viewerCount']}"
    if msg_type == "HOST":
        raw_msg = f"{etags['msg-param-displayName']} is hosting for " \
                  f"{etags['msg-param-viewerCount']} viewers"

    # system-messages are escaped, lets fix that
    if 'system-msg' in etags:
        etags['system-msg'] = html.unescape(etags['system-msg'].replace("\\s", " "))

    if hasattr(event, "_command"):
        other = commands.handle_other_commands(event)
        if other:
            return other

    if raw_msg.startswith('\u0001'):
        # Strip "\001ACTION"
        raw_msg = raw_msg.replace('\u0001', "")[7:]
    else:
        extra.append("quoted")

    if raw_msg.startswith('!'):
        # Don't render commands
        return {}

    nickname = etags['display-name'] if 'display-name' in etags else ''

    badges = []
    if "badges" in etags and etags["badges"]:
        badges = await render_badges(event.channel, etags['badges'])

    if 'emotes' in etags and etags["emotes"]:
        message = render_emotes(raw_msg, etags['emotes'])
    else:
        # Render emotes escapes it's output already
        message = html.escape(raw_msg)

    message = bleach.linkify(message)

    if "bits" in etags:
        message = await render_bits(message, etags["bits"])

    return {
            'badges': badges,
            'nickname': nickname,
            'message' : message,
            'orig_message': orig_message,
            'id' : etags['id'],
            'tags' : etags,
            'type' : msg_type,
            'channel' : event.channel,
            'extra' : extra
            }

def create_event(from_evt, message):
    new_evt = copy.copy(from_evt)
    new_evt.message = message
    return new_evt
