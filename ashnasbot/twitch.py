import bisect
import copy
import html
import json
import logging
import re
import sys

from . import av
from . import commands

STATIC_CDN = "https://static-cdn.jtvnw.net/"

ACTION="action"

BADGES = {
    'admin': STATIC_CDN + "chat-badges/admin-alpha.png",
    'bits': STATIC_CDN + "badges/v1/09d93036-e7ce-431c-9a9e-7044297133f2/1",
    'broadcaster': STATIC_CDN + "chat-badges/broadcaster-alpha.png",
    'global_mod': STATIC_CDN + "badges/v1/9384c43e-4ce7-4e94-b2a1-b93656896eba/1",
    'moderator': STATIC_CDN + "chat-badges/mod-alpha.png",
    'subscriber': STATIC_CDN + "badges/v1/5d9f2208-5dd8-11e7-8513-2ff4adfae661/1",
    'staff': STATIC_CDN + "chat-badges/staff-alpha.png",
    'turbo': STATIC_CDN + "chat-badges/turbo-alpha.png",
    'partner': STATIC_CDN + "badges/v1/d12a2e27-16f6-41d0-ab77-b780518f00a3/1",
    'premium': STATIC_CDN + "badges/v1/a1dd5073-19c3-4911-8cb4-c464a7bc1510/1",
    'vip': STATIC_CDN + "badges/v1/b817aba4-fad8-49e2-b88a-7cc744dfa6ec/1"
}

EMOTE_URL_TEMPLATE = "<img src=\"" + STATIC_CDN + \
"""emoticons/v1/{eid}/1.5" class="emote" 
alt="{alt}"
title="{alt}"
/>"""

CHEERMOTE_URL_TEMPLATE = "<img src=\"" + STATIC_CDN + \
"""bits/dark/animated/{color}/1.5" class="emote" 
alt="{alt}"
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
        
def render_badges(badges):
    rendered = []
    for badgever in badges.split(','):
        badge, _ = badgever.split('/')
        url = BADGES.get(badge, None)
        if not url:
            continue
        rendered.append(BADGE_URL_TEMPLATE.format(url=url, alt=badge))

    return rendered

def render_bits(message, bits):
    def render_cheer(match):
        ammount = match.group(3)
        bits_indecies = [ v for v, c in BITS_COLORS]
        _, color = BITS_COLORS[bisect.bisect_right(bits_indecies, int(ammount)) - 1]
        return CHEERMOTE_URL_TEMPLATE.format(color=color, alt=f"Cheer{ammount}") + \
               CHEERMOTE_TEXT_TEMPLATE.format(text=ammount, color=color)

    # TODO: compile
    cheer_regex = r"(^|\s)(?P<emotename>[a-zA-Z]+)(\d+)(\s|$)"
    match = re.search(cheer_regex, message)
    if not match:
        logger.warn("Cannot find bits in message")
    elif match.group('emotename').lower().startswith('cheer'):
        message = re.sub(cheer_regex, render_cheer, message, flags=re.IGNORECASE)
    else:
        logger.warn("Non cheer bits message used")
    return message

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
            channel = re.search(r"^#(\w+)\s", event._params).group(1)
            return {
                    'nickname': etags['login'],
                    'orig_message': event._params,
                    'id' : etags['target-msg-id'],
                    'type' : event._command,
                    'channel' : channel
                    }
        elif event._command == "CLEARCHAT":
            channel, nick = re.search(r"^#(\w+)\s:(\w+)$", event._params).groups()
            return {
                    'nickname': nick,
                    'type' : event._command,
                    'channel' : channel
                    }
        elif evt._command == "RECONNECT":
            ret_event = ResponseEvent()
            logger.warn("Twitch chat is going down")
            ret_event.message = "Twitch chat is going down"
        elif evt._command == "HOSTTARGET":
            ret_event = ResponseEvent()
            if re.search(r"HOSTTARGET\s#\w+\s:-", evt.message):
                # TODO: Store channels hosting
                ret_event['message'] = "Stopped hosting"
            else:
                channel = re.search(r"HOSTTARGET\s#\w+\s(\w+)\s", evt.message).group(1)
                ret_event['message'] = f"Hosting {channel}"
            logger.info(ret_evt['message'])

    except:
        return


def handle_message(event):
    etags = event.tags
    raw_msg = ""
    try:
        raw_msg = event.message
    except:
        event.message = ""
    if event.type == "RAID":
        raw_msg = f"{etags['msg-param-displayName']} is raiding with a party of " \
                  f"{etags['msg-param-viewerCount']}"
    if event.type == "HOST":
        raw_msg = f"{etags['msg-param-displayName']} is hosting for " \
                  f"{etags['msg-param-viewerCount']} viewers"
    if event.type == "SUB":
        raw_msg = html.unescape(etags['system-msg'].replace("\\s", " "))

    other = handle_other_commands(event)
    if other:
        return other

    msg_tags = []
    msg_type = event.type

    if raw_msg.startswith('\u0001'):
        # Strip "\001ACTION"
        raw_msg = raw_msg.replace('\u0001', "")[7:]
        msg_tags.append(ACTION)

    if raw_msg.startswith('!'):
        # Don't render commands
        return {}

    nickname = ''
    if 'display-name' in etags:
        nickname = etags['display-name']

    badges = []
    if etags['badges']:
        badges = render_badges(etags['badges'])

    if etags['emotes']:
        message = render_emotes(raw_msg, etags['emotes'])
    else:
        message = html.escape(raw_msg)

    if "bits" in etags:
        logger.info(raw_msg)
        message = render_bits(message, etags["bits"])

    return {
            'badges': badges,
            'nickname': nickname,
            'message' : message,
            'orig_message': event.message,
            'id' : etags['id'],
            'tags' : etags,
            'extra' : msg_tags,
            'type' : msg_type,
            'channel' : event.channel
            }

COMMANDS = {
    # '!hey': lambda *args: av.play_random_sound('OOT_Navi_')
    '!no': commands.no_cmd,
    '!so': commands.so_cmd,
    '!praise': commands.praise_cmd
}

def create_event(from_evt, message):
    new_evt = copy.copy(from_evt)
    new_evt.message = message
    return new_evt
