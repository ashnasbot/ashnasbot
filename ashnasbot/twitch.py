import bisect
import copy
import html
import json
import logging
import re
import sys

import dataset
from .twitch_client import TwitchClient

from . import av
from . import commands

db = dataset.connect('sqlite:///twitchdata.db')

STATIC_CDN = "https://static-cdn.jtvnw.net/"

ACTION="action"

BADGES = {
    'admin': STATIC_CDN + "chat-badges/admin-alpha.png",
    'bits1': STATIC_CDN + "/badges/v1/73b5c3fb-24f9-4a82-a852-2f475b59411c/2",
    'bits100': STATIC_CDN + "badges/v1/09d93036-e7ce-431c-9a9e-7044297133f2/2",
    'bits1000': STATIC_CDN + "badges/v1/0d85a29e-79ad-4c63-a285-3acd2c66f2ba/2",
    'bits5000': STATIC_CDN + "badges/v1/57cd97fc-3e9e-4c6d-9d41-60147137234e/2",
    'bits10000': STATIC_CDN + "badges/v1/68af213b-a771-4124-b6e3-9bb6d98aa732/2",
    'bits25000': STATIC_CDN + "badges/v1/64ca5920-c663-4bd8-bfb1-751b4caea2dd/2",
    'broadcaster': STATIC_CDN + "chat-badges/broadcaster-alpha.png",
    'global_mod': STATIC_CDN + "badges/v1/9384c43e-4ce7-4e94-b2a1-b93656896eba/2",
    'moderator': STATIC_CDN + "chat-badges/mod-alpha.png",
    'subscriber': STATIC_CDN + "badges/v1/5d9f2208-5dd8-11e7-8513-2ff4adfae661/2",
    'staff': STATIC_CDN + "chat-badges/staff-alpha.png",
    'turbo': STATIC_CDN + "chat-badges/turbo-alpha.png",
    'partner': STATIC_CDN + "badges/v1/d12a2e27-16f6-41d0-ab77-b780518f00a3/2",
    'premium': STATIC_CDN + "badges/v1/a1dd5073-19c3-4911-8cb4-c464a7bc1510/2",
    'vip': STATIC_CDN + "badges/v1/b817aba4-fad8-49e2-b88a-7cc744dfa6ec/2"
}

EMOTE_URL_TEMPLATE = "<img src=\"" + STATIC_CDN + \
"""emoticons/v1/{eid}/1.5" class="emote" 
alt="{alt}"
title="{alt}"
/>"""

#CHEERMOTE_URL_TEMPLATE = "<img src=\"" + STATIC_CDN + \
#"""bits/dark/animated/{color}/1.5" class="emote" 
#alt="{alt}"
#title="{alt}"
#/>"""
CHEERMOTE_URL_TEMPLATE = "<img src=\"{url}\" class=\"emote\"" + \
"""alt="{alt}"
title="{alt}"
/>"""

CHEERMOTE_TEXT_TEMPLATE = """<span class="cheertext-{color}">{text}</span> """

BADGE_URL_TEMPLATE = """<img class="badge" src="{url}"
alt="{alt}"
title="{alt}"
/>"""

BITS_COLORS = [
    (1, 'gray'),
    (100, 'purple'),
    (1000, 'green'),
    (5000, 'blue'),
    (10000, 'red'),
]
BITS_INDICIES = [1, 100, 1000, 5000, 10000]

logger = logging.getLogger(__name__)

class ResponseEvent(dict):
    """Render our own msgs through the bot."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__dict__ = self
        self.nickname = "Ashnasbot"
        self.tags = {
            'display-name': 'Ashnasbot',
            'badges': [],
            'emotes': [],
            'id': 'bot',
            'user-id': 275857969
        }
        self.type = 'TWITCHCHATMESSAGE'


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
        if badge == 'bits':
            logger.info(f"Bits badge: {val}")
            url = BADGES.get(badge + val, None)
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
        real_value = match.group(3)
        emote_name = match.group('emotename')
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
    cheer_regex = r"(^|\s)(?P<emotename>[a-zA-Z]+)(\d+)(\s|$)"
    match = re.search(cheer_regex, message)
    if not match:
        logger.warn("Cannot find bits in message")
        return message

    return re.sub(cheer_regex, render_cheer, message, flags=re.IGNORECASE)
    
def handle_command(event):
    etags = event.tags
    raw_msg = event.message
    logger.info(f"{etags['display-name']} COMMAND: {raw_msg}")
    args = raw_msg.split(" ")
    command = args.pop(0)
    cmd = COMMANDS.get(command, None)

    ret_event = ResponseEvent()
    ret_event.channel = event.channel
    ret_event.tags['caller'] = event.tags['display-name']
    if callable(cmd):
        ret_event = cmd(ret_event, *args)
        return ret_event

def handle_other_commands(event):
    try:
        if event._command == "CLEARMSG":
            return {
                    'nickname': etags['login'],
                    'orig_message': event._params,
                    'id' : etags['target-msg-id'],
                    'type' : event._command,
                    }
        elif event._command == "CLEARCHAT":
            channel, nick = re.search(r"^#(\w+)\s:(\w+)$", event._params).groups()
            return {
                    'nickname': nick,
                    'type' : event._command,
                    'channel' : channel
                    }
        elif event._command == "RECONNECT":
            ret_event = ResponseEvent()
            logger.warn("Twitch chat is going down")
            ret_event.message = "Twitch chat is going down"
            return ret_event
        elif event._command == "HOSTTARGET":
            ret_event = ResponseEvent()
            if event.message == "-":
                # TODO: Store channels hosting
                ret_event['message'] = "Stopped hosting"
            else:
                channel = re.search(r"(\w+)\s[\d-]+", event.message).group(1)
                ret_event['message'] = channel
                ret_event['type'] = "HOST"
            logger.info(ret_event['message'])
            return ret_event

    except:
        return

async def handle_message(event):
    etags = event.tags if hasattr(event, "tags") else {}
    raw_msg = event.message if hasattr(event, "message") else ""
    orig_message = raw_msg
    msg_type = event.type


    if msg_type == "RAID":
        raw_msg = f"{etags['msg-param-displayName']} is raiding with a party of " \
                  f"{etags['msg-param-viewerCount']}"
    if msg_type == "HOST":
        raw_msg = f"{etags['msg-param-displayName']} is hosting for " \
                  f"{etags['msg-param-viewerCount']} viewers"

    # system-messages are escaped, lets fix that
    if not raw_msg and 'system-msg' in etags:
        raw_msg = html.unescape(etags['system-msg'].replace("\\s", " "))

    if hasattr(event, "_command"):
        other = handle_other_commands(event)
        if other:
            return other

    if raw_msg.startswith('\u0001'):
        # Strip "\001ACTION"
        raw_msg = raw_msg.replace('\u0001', "")[7:]

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
            'channel' : event.channel
            }

COMMANDS = {
    '!no': commands.no_cmd,
    '!so': commands.so_cmd,
    '!praise': commands.praise_cmd,
    '!deaths': commands.death_cmd
}

def create_event(from_evt, message):
    new_evt = copy.copy(from_evt)
    new_evt.message = message
    return new_evt
