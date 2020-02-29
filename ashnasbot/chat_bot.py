import logging
import time
import functools
import re
from threading import Thread, current_thread, Event
from concurrent.futures import Future

import traceback
import asyncio
from twitchobserver import Observer

from . import twitch
from .twitch import commands

logger = logging.getLogger(__name__)

class ChatBot():
    evt_filter = ["TWITCHCHATJOIN", "TWITCHCHATMODE", "TWITCHCHATMESSAGE",
                  "TWITCHCHATUSERSTATE", "TWITCHCHATROOMSTATE", "TWITCHCHATLEAVE"]
    evt_types = ["TWITCHCHATMESSAGE"]
    handled_commands = ["CLEARMSG", "RECONNECT", "HOSTTARGET", "CLEARCHAT"]

    def __init__(self, loop, bot_user, oauth):
        self.notifications = []
        self.channels = set()
        self.observer = Observer(bot_user, oauth)
        self.observer._inbound_poll_interval = 0
        self.observer.start()
        self.loop = loop

        self.chat_queue = asyncio.Queue(maxsize=100, loop=loop)
        self.alert_queue = asyncio.Queue(maxsize=100, loop=loop)
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
            logger.debug(f"Already subbed to channel: {channel}")

    def unsubscribe(self, channel):
        logger.debug(f"unsubscribe: {channel}")
        self.observer.leave_channel(channel)
        if channel not in self.channels:
            logger.warn(f"unsubscribing from channel not subbed: {channel}")
            logging.debug(traceback.format_stack())
        else:
            logger.info(f"Leaving channel: {channel}")
            self.channels.remove(channel)

    def alerts(self):
        return self.alert_queue

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

        f = functools.partial(asyncio.ensure_future, coro, loop=self.loop)
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
                logger.info(f"SUB {evt.tags['display-name']} subbed")
            elif msg_id == "resub":
                evt.type = "SUB"
                logger.info(f"SUB {evt.tags['display-name']} subbed for {evt.tags['msg-param-cumulative-months']} months")
            elif msg_id == "subgift":
                logger.info(f"SUB {evt.tags['display-name']} gifted a sub to {evt.tags['msg-param-recipient-display-name']}")
                evt.type = "SUBGIFT"
            elif msg_id == "raid":
                logger.info(f"RAID {evt.tags['display-name']} raiding with a party of {evt.tags['msg-param-viewerCount']}")
                evt.type = "RAID"
            elif msg_id == "host":
                evt.type = "HOST"
                logger.info(f"HOST {evt}")

            try:
                self.add_task(self.chat_queue.put(evt))
            except asyncio.QueueFull:
                logger.error("Queue full, discarding alert")

        elif evt.type == "TWITCHCHATCOMMAND" or \
             evt.type == "TWITCHCHATCLEARCHAT" or \
             evt.type == "TWITCHCHATHOSTTARGET":
            if evt._command in self.handled_commands:
                logger.debug(evt._command)
                self.add_task(self.chat_queue.put(evt))

    def send_message(self, message, channel):
        if not message:
            return
        if channel not in self.channels:
            logger.warn("Sending a message to a channel we're not in: {channel}")
            self.observer.join_channel(channel)

        self.observer.send_message(message, channel)

        if channel not in self.channels:
            self.observer.leave_channel(channel)

    def close(self):
        for c in self.channels:
            logger.info(f"closing chat {c}")
            self.observer.leave_channel(c)
