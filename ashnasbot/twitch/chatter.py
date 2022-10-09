import asyncio
import logging
import random
import string


from . import bttv
from . import commands
from . import OWN_EMOTES
from .data import EMOTE_FULL_TEMPLATE, create_event
from ..config import Config

logger = logging.getLogger(__name__)


class ChatChatter():
    """ Allows bot to send messages and respond."""

    def __init__(self, add_event):
        self.add_event = add_event  # func to call to inject messages

    async def timer(self):
        while True:
            await asyncio.sleep(random.randint(30, 300) == 10)
            evt = self.make_message("")
            commands.common.chat_cmd(evt, "test")
            self.add_event(evt)

    async def handle_message(self, event, cid=None):
        if event.message in OWN_EMOTES:
            emote = event.message
            evt = self.make_message(event.channel, emote)
            url = OWN_EMOTES[emote][1]
            evt.orig_message = EMOTE_FULL_TEMPLATE.format(url=url, alt=emote)
            await self.add_event(evt)
            logger.debug("RESPONSE %s %s", evt.message, evt)
            return

        bttv_emotes = await bttv.get_emotes(cid)
        if event.message in bttv_emotes:
            emote = event.message
            evt = self.make_message(event.channel, emote)
            url = bttv_emotes[emote]
            evt.orig_message = url
            await self.add_event(evt)
            logger.debug("RESPONSE %s %s", evt.message, evt)
            return

        # 1/30 borrowed from buttsbot
        if random.randint(1, 30) == 1:
            evt = self.make_message(event.channel)
            wordlist = event.message.translate(str.maketrans('', '', string.punctuation)).split(" ")
            shortlist = [i for i in wordlist if len(i) > 3]
            if not shortlist:
                shortlist = wordlist
            prompt = random.choice(shortlist)

            # !chat expects an output event - i.e. dict based
            content = {}
            commands.common.chat_cmd(content, prompt)
            evt.message = content["message"]

            await self.add_event(evt)
            logger.debug("RESPONSE %s %s", evt.message, evt)
            return

    def make_message(self, channel, message=""):
        msg = create_event('TWITCHCHATMESSAGE', message)
        username = Config()["username"]
        msg.channel = channel
        msg.nickname = username
        msg.tags["display-name"] = username
        msg.tags["response"] = True
        return msg
