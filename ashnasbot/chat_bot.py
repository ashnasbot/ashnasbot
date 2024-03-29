import logging
import functools
from concurrent.futures import Future
import time

import asyncio
from twitchobserver import Observer

logger = logging.getLogger(__name__)


class ChatBot():
    evt_filter = ["TWITCHCHATJOIN", "TWITCHCHATMODE", "TWITCHCHATMESSAGE",
                  "TWITCHCHATROOMSTATE", "TWITCHCHATLEAVE"]
    handled_commands = ["CLEARMSG", "RECONNECT", "CLEARCHAT"]

    def __init__(self, loop, bot_user, oauth):
        self.channels = set()
        self.observer = Observer(bot_user, oauth)
        self.observer._inbound_poll_interval = 0
        self.emotesets = set()
        retry = 5
        while retry:
            try:
                self.observer.start()
                break
            except Exception as e:
                print(e)
                time.sleep(2)
                retry -= 1
                continue
        self.loop = loop

        self.chat_queue = asyncio.Queue(maxsize=100)
        self.observer.subscribe(self.handle_event)

    def subscribe(self, channel):
        logger.debug(f"Subscribe: {channel}")
        if not self.observer._socket:
            logger.error("Twitch chat Socket not connected,"
                         " Attempting to reconnect.")
            self.observer.stop()
            self.observer.start()
        if channel not in self.channels:
            logger.info(f"Joining channel: {channel}")
            self.observer.join_channel(channel)
            self.channels.add(channel)
        else:
            # Expected when joining for chat and alerts
            logger.debug(f"Already subbed to channel: {channel}")

    def unsubscribe(self, channel):
        logger.debug(f"Unsubscribe: {channel}")
        self.observer.leave_channel(channel)
        if channel not in self.channels:
            logger.debug(f"Unsubscribing from channel not subbed: {channel}")
        else:
            logger.info(f"Leaving channel: {channel}")
            self.channels.remove(channel)

    def chat(self):
        return self.chat_queue

    def add_task(self, coro):
        """Add a task into a loop on another thread."""
        def _async_add(func, fut):
            try:
                ret = func()
                fut.set_result(ret)
            except Exception as e:
                fut.set_exception(e)

        f = functools.partial(self.loop.create_task, coro)
        # We're in a non-event loop thread so we use a Future
        # to get the task from the event loop thread once
        # it's ready.
        fut = Future()
        self.loop.call_soon_threadsafe(_async_add, f, fut)
        return fut.result()

    def handle_event(self, evt):
        logger.debug(evt)

        if evt.type == 'TWITCHCHATMESSAGE':
            try:
                self.add_task(self.chat_queue.put(evt))
            except asyncio.QueueFull:
                logger.error("Queue full, discarding message")
            return

        elif evt.type in self.evt_filter:
            return

        elif evt.type == "TWITCHCHATUSERNOTICE":
            msg_id = evt.tags['msg-id']
            if msg_id == "charity":
                logger.info("Chraity stuff")
            elif msg_id == "sub":
                evt.type = "SUB"
                logger.info(f"SUB {evt.tags['display-name']} subscribed")
            elif msg_id == "resub":
                evt.type = "SUB"
                logger.info(f"SUB {evt.tags['display-name']} subscribed for "
                            f"{evt.tags['msg-param-cumulative-months']} months")
            elif msg_id == "subgift":
                logger.info(f"SUB {evt.tags['display-name']} gifted a subscription to "
                            f"{evt.tags['msg-param-recipient-display-name']}")
                evt.type = "SUBGIFT"
            elif msg_id == "raid":
                logger.info(f"RAID {evt.tags['display-name']} is raiding with a party of "
                            f"{evt.tags['msg-param-viewerCount']}")
                evt.type = "RAID"

            try:
                self.add_task(self.chat_queue.put(evt))
            except asyncio.QueueFull:
                logger.error("Queue full, discarding alert")

        elif evt.type == "TWITCHCHATCOMMAND" or \
                evt.type == "TWITCHCHATCLEARCHAT":
            if evt._command in self.handled_commands:
                logger.debug(evt._command)
                self.add_task(self.chat_queue.put(evt))
        elif evt.type == "TWITCHCHATUSERSTATE":
            self.emotesets = set(evt.tags["emote-sets"].split(","))
            self.badges = evt.tags["badges"]  # no split, handled by renderer

    def send_message(self, message, channel, tags=None):
        if not message:
            return
        if channel not in self.channels:
            logger.warn("Sending a message to a channel we're not in: {channel}")
            self.observer.join_channel(channel)

        self.observer.send_message(message, channel, tags)

        if channel not in self.channels:
            self.observer.leave_channel(channel)

    def close(self):
        for c in self.channels:
            logger.info(f"Closing chat {c}")
            self.observer.leave_channel(c)
        self.observer.stop()
