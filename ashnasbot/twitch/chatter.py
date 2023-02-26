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
        evt = self.make_message(event.channel)
        bttv_emotes = await bttv.get_emotes(cid)
        generated = False
        content = {}
        if event.message in OWN_EMOTES:
            if random.randint(1, 3) == 1:
                emote = event.message
                evt.message = emote
                url = OWN_EMOTES[emote][1]
                evt.orig_message = EMOTE_FULL_TEMPLATE.format(url=url, alt=emote)

        elif event.message in bttv_emotes:
            if random.randint(1, 3) == 1:
                emote = event.message
                evt.message = emote
                url = bttv_emotes[emote]
                evt.orig_message = url

        elif event.message.lower().startswith("@ashnasbot"):
            commands.common.chat_cmd(content, event.message[10:])
            evt.tags["reply-parent-msg-id"] = event.tags["id"]
            evt.message = content["message"]
            generated = True

        elif 'reply-parent-user-login' in event.tags and \
                event.tags['reply-parent-user-login'] == "ashnasbot":
            generated = True
            if event.message.lower().strip('@') == "ashnasbot yes":
                evt.message = ":)"
            elif event.message.lower().strip('@') == "ashnasbot no":
                evt.message = ":("
            else:
                evt.tags["reply-parent-msg-id"] = event.tags["id"]
                wordlist = event.message.translate(str.maketrans('', '', string.punctuation)).split(" ")
                shortlist = [i for i in wordlist if i.lower() != "ashnasbot"]
                if not shortlist:
                    shortlist = wordlist
                prompt = random.choice(shortlist)
                if random.randint(1, 3) <= 2:
                    prompt += " "

                commands.common.chat_cmd(content, prompt)
                evt.message = content["message"]

        # 1/30 borrowed from buttsbot
        elif random.randint(1, 30) == 1:
            wordlist = event.message.translate(str.maketrans('', '', string.punctuation)).split(" ")
            shortlist = [i for i in wordlist]
            if not shortlist:
                shortlist = wordlist
            prompt = random.choice(shortlist)

            commands.common.chat_cmd(content, prompt)
            evt.message = content["message"]
            generated = True

        if generated:
            logger.debug("RESPONSE %s %s", evt.message, evt)
            await self.add_event(evt)

    def make_message(self, channel, message=""):
        msg = create_event('TWITCHCHATMESSAGE', message)
        username = Config()["username"]
        msg.channel = channel
        msg.nickname = username
        msg.tags["display-name"] = username
        msg.tags["response"] = True
        return msg
