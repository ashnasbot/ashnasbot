import asyncio
import html
import logging
import random
import re

from . import bttv
from . import commands
from . import OWN_EMOTES
from .data import EMOTE_FULL_TEMPLATE, Event, EventType
from ..config import Config

logger = logging.getLogger(__name__)
NAME_REPLACE = re.compile(re.escape('@ashnasbot'), re.IGNORECASE)
AT_MENTION = re.compile(r'@\w+')

MAX_STORE = 500


class ChatChatter():
    """ Allows bot to send messages and respond."""

    def __init__(self, add_event):
        self.add_event = add_event  # func to call to inject messages
        self.buffer = []
        self.message_store = {}  # msg_id -> {name, text, parent_id, is_bot}

    def _store_message(self, msg_id, display_name, text, parent_id=None, is_bot=False):
        self.message_store[msg_id] = {
            "name": display_name,
            "text": text,
            "parent_id": parent_id,
            "is_bot": is_bot,
        }
        if len(self.message_store) > MAX_STORE:
            del self.message_store[next(iter(self.message_store))]

    def _build_thread(self, event, max_turns=10):
        """Walk the reply chain and return ordered (role, text) pairs."""
        chain = []
        parent_id = event.tags.get("reply-parent-msg-id")
        while parent_id and len(chain) < max_turns:
            msg = self.message_store.get(parent_id)
            if not msg:
                break
            role = "assistant" if msg["is_bot"] else "user"
            text = msg["text"] if msg["is_bot"] else f"{msg['name']}: {msg['text']}"
            chain.append((role, text))
            parent_id = msg.get("parent_id")
        chain.reverse()
        return chain

    async def warmup(self):
        await asyncio.to_thread(commands.common.preload_model)

    async def handle_message(self, event, cid=None):
        bot_username = Config().get("username", "ashnasbot").lower()
        msg_id = event.tags.get("id")
        display_name = event.tags.get("display-name", event.nickname or "")
        parent_id = event.tags.get("reply-parent-msg-id")
        is_bot = bool(event.nickname and event.nickname.lower() == bot_username)

        # Store every message (including reflected bot messages) for thread lookups
        if msg_id:
            fragments = event.tags.get("_fragments", [])
            if fragments:
                stored_text = "".join(f["text"] for f in fragments if f.get("type") == "text").strip()
                stored_text = (AT_MENTION.sub("", stored_text).strip()
                               or AT_MENTION.sub("", event.message).strip())
            else:
                stored_text = AT_MENTION.sub("", event.message).strip()
            self._store_message(msg_id, display_name, stored_text, parent_id, is_bot)

        # Don't respond to our own reflected messages
        if is_bot:
            return

        evt = self.make_message(event.channel)
        bttv_emotes = await bttv.get_emotes(cid) or {}
        generated = False
        fragments = event.tags.get("_fragments", [])
        if fragments:
            text_only = "".join(f["text"] for f in fragments if f.get("type") == "text")
            instr = NAME_REPLACE.sub("", text_only).strip() or NAME_REPLACE.sub("", event.message).strip()
        else:
            instr = NAME_REPLACE.sub("", event.message).strip()
        trigger = f"{display_name}: {instr}"
        self.buffer.append(trigger)
        ctx = int(Config().get("chat_context_messages", 10))
        self.buffer = self.buffer[-ctx:]

        # React to good/bad bot commands
        if instr.lower() in ("!good_bot", "!goodbot"):
            evt.tags["reply-parent-msg-id"] = msg_id
            evt.message = await asyncio.to_thread(
                commands.common.generate_chat_message, self.buffer,
                f"{display_name} called you a good bot", None, event.channel)
            generated = True

        elif instr.lower() in ("!bad_bot", "!badbot"):
            evt.tags["reply-parent-msg-id"] = msg_id
            evt.message = await asyncio.to_thread(
                commands.common.generate_chat_message, self.buffer,
                f"{display_name} called you a bad bot", None, event.channel)
            generated = True

        # Reply to bare emotes
        elif instr in OWN_EMOTES:
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

        # Reply in a thread where the bot was the parent
        elif 'reply-parent-user-login' in event.tags and \
                event.tags['reply-parent-user-login'] == bot_username:
            generated = True
            if instr.lower() == "yes":
                evt.message = ":)"
            elif instr.lower() == "no":
                evt.message = ":("
            else:
                evt.tags["reply-parent-msg-id"] = msg_id
                thread = self._build_thread(event)
                evt.message = await asyncio.to_thread(
                    commands.common.generate_chat_message, self.buffer, trigger, thread, event.channel)

        # Reply to general @bot mention
        elif bot_username in event.message.lower():
            evt.tags["reply-parent-msg-id"] = msg_id
            evt.message = await asyncio.to_thread(
                commands.common.generate_chat_message, self.buffer, trigger, None, event.channel)
            generated = True

        # Random 1/30 interjection
        elif random.randint(1, 30) == 1:
            evt.message = await asyncio.to_thread(
                commands.common.generate_chat_message, self.buffer, None, None, event.channel)
            generated = True

        if generated:
            logger.debug("%s", evt)
            evt.message = html.escape(evt.message)
            await self.add_event(evt)

    def make_message(self, channel, message=""):
        msg = Event(EventType.TWITCHCHATMESSAGE, message)
        username = Config()["username"]
        msg.channel = channel
        msg.nickname = username
        msg.tags["display-name"] = username
        msg.tags["response"] = True
        return msg
