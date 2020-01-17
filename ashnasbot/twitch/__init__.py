import bisect
import copy
import html
import json
import logging
import re
import sys
import time

import bleach

from .api_client import TwitchClient
from .data import *
from . import commands
from . import db

CHEER_REGEX = re.compile(r"((?<=^)|(?<=\s))(?P<emotename>[a-zA-Z]+)(\d+)(?=(\s|$))", flags=re.IGNORECASE)


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
    tbl_name = channel + "_badges"
    if not db.exists(tbl_name):
        db.create(tbl_name, 
                  primary="name")

    if db.expired(channel + "_badges"):
        logger.info("No badge cache for %s", channel)
        client = TwitchClient(None, None)
        badges = await client.get_badges_for_channel(channel)
        rows = [{"name":k, "url":v} for k,v in badges.items()]
        keys = ["name"]

        db.update_multi(tbl_name, rows, keys)

    ret = {}
    for badge in db.get(tbl_name):
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

    if not db.exists("cheermotes"):
        db.create("cheermotes", ["cheer", "value"])

    for record in data:
        db.update("cheermotes", record, ["cheer", "value"])

    return db.find("cheermotes", cheer=cheer, value=value)

def get_le(collection, val):
    """Get the item in collection less than or equal to val."""
    return collection[bisect.bisect_right(collection, int(val)) - 1]
        
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
            badge = badge + str(get_le(SUB_TIERS, val))
            url = channel_badges.get(badge, None)
        elif badge in ['bits', 'bits-leader', 'sub-gift-leader']:
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
    if not CHEERMOTES or db.expired("cheermotes"):
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

    match = CHEER_REGEX.search(message)
    if not match:
        logger.warn("Cannot find bits in message")
        return message

    return CHEER_REGEX.sub(render_cheer, message)
    
URL_REGEX = re.compile(r"(http(s)?://)?(clips.twitch.tv/(\w+)|www.twitch.tv/\w+/clip/(\w+))", flags=re.IGNORECASE)
async def render_clips(message):
    client = TwitchClient(None, None)
    match = URL_REGEX.search(message)
    slug = match.group(4)
    if slug is None:
        slug = match.group(5)
    if slug is None:
        logger.error("Malformed clip url %s", match.groups())
        return message

    details = await client.get_clip(slug)

    def render(match):
        thumbnail = details["thumbnails"]["small"]
        title = details["title"]
        clipped_by = f'clipped by {details["curator"]["display_name"]}'
        return f'''{match.group(0)}</br>
            <div class="inner_frame"><img src="{thumbnail}"/>
            <span class="title">{title}</span>
            <span>{clipped_by}</span></div>'''
    return URL_REGEX.sub(render, message)

async def handle_message(event):
    etags = event.tags if hasattr(event, "tags") else {}
    raw_msg = event.message if hasattr(event, "message") else ""
    orig_message = raw_msg
    msg_type = event.type
    quoted = True

    extra = []

    if raw_msg.startswith('!'):
        return commands.handle_command(event)

    if msg_type == "RAID":
        raw_msg = f"{etags['msg-param-displayName']} is raiding with a party of " \
                  f"{etags['msg-param-viewerCount']}"
    if msg_type == "HOST":
        raw_msg = f"{etags['msg-param-displayName']} is hosting for " \
                  f"{etags['msg-param-viewerCount']} viewers"


    if hasattr(event, "_command"):
        other = commands.handle_other_commands(event)
        if other:
            return other

    if raw_msg.startswith('\u0001'):
        # Strip "\001ACTION" off /me
        raw_msg = raw_msg.replace('\u0001', "")[7:]
        quoted = False

    if 'system-msg' in etags:
        # system-messages are escaped, lets fix that
        etags['system-msg'] = html.unescape(etags['system-msg'].replace("\\s", " "))
        quoted = False

    if quoted:
        extra.append("quoted")

    nickname = etags['display-name'] if 'display-name' in etags else ''

    badges = []
    if "badges" in etags and etags["badges"]:
        badges = await render_badges(event.channel, etags['badges'])

    if 'emotes' in etags and etags["emotes"]:
        message = render_emotes(raw_msg, etags['emotes'])
    else:
        # render_emotes escapes its output already
        message = html.escape(raw_msg)

    if re.match(URL_REGEX,message):
        message = await render_clips(message)

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
