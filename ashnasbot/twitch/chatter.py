import asyncio
import html
import logging
import random
import re

from . import bttv
from . import commands
from . import OWN_EMOTES
from .data import EMOTE_FULL_TEMPLATE, create_event
from ..config import Config

logger = logging.getLogger(__name__)
NAME_REPLACE = re.compile(re.escape('@ashnasbot'), re.IGNORECASE)


class ChatChatter():
    """ Allows bot to send messages and respond."""

    def __init__(self, add_event):
        self.add_event = add_event  # func to call to inject messages
        self.buffer = []

    async def timer(self):
        while True:
            await asyncio.sleep(random.randint(30, 300) == 10)
            evt = self.make_message("")
            commands.common.generate_chat_message(evt, ["test"])
            self.add_event(evt)

    async def handle_message(self, event, cid=None):
        evt = self.make_message(event.channel)
        bttv_emotes = await bttv.get_emotes(cid)
        generated = False
        content = {}
        instr = NAME_REPLACE.sub("", event.message).strip()
        self.buffer.append(instr)
        self.buffer = self.buffer[-10:]
        # Reply to bare emotes
        if instr in OWN_EMOTES:
            if random.randint(1, 3) == 1:
                emote = instr
                evt.message = emote
                url = OWN_EMOTES[emote][1]
                evt.orig_message = EMOTE_FULL_TEMPLATE.format(url=url, alt=emote)
        elif instr in bttv_emotes:
            if random.randint(1, 3) == 1:
                emote = instr
                evt.message = emote
                url = bttv_emotes[emote]
                evt.orig_message = url

        # reply to @bot message
        elif 'reply-parent-user-login' in event.tags and \
                event.tags['reply-parent-user-login'] == "ashnasbot":  # TODO: parameterise
            generated = True
            if instr.lower() == "yes":
                evt.message = ":)"
            elif instr.lower() == "no":
                evt.message = ":("
            else:
                evt.tags["reply-parent-msg-id"] = event.tags["id"]
                commands.common.generate_chat_message(content, self.buffer)
                evt.message = content["message"]

        # reply to general @bot
        elif "@ashnasbot" in event.message.lower():
            commands.common.generate_chat_message(content, self.buffer)
            evt.tags["reply-parent-msg-id"] = event.tags["id"]
            evt.message = content["message"]
            generated = True

        # random 1/30 borrowed from buttsbot
        elif random.randint(1, 30) == 1:
            commands.common.generate_chat_message(content, self.buffer)
            evt.message = content["message"]
            generated = True

        if generated:
            logger.debug("Generated: %s", content["message"])
            logger.debug("RESPONSE %s", evt.message)
            logger.debug("%s", evt)
            evt.message = html.escape(evt.message)
            await self.add_event(evt)

    def make_message(self, channel, message=""):
        msg = create_event('TWITCHCHATMESSAGE', message)
        username = Config()["username"]
        msg.channel = channel
        msg.nickname = username
        msg.tags["display-name"] = username
        msg.tags["response"] = True
        return msg
