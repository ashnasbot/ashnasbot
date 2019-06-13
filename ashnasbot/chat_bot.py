import logging
import time
import functools
import re
from threading import Thread, current_thread, Event
from concurrent.futures import Future

#Remove me
import traceback

import asyncio

from twitchobserver import Observer

from . import twitch

logger = logging.getLogger(__name__)

class ChatBot():
    evt_filter = ["TWITCHCHATJOIN", "TWITCHCHATMODE", "TWITCHCHATMESSAGE",
                  "TWITCHCHATCOMMAND", "TWITCHCHATUSERSTATE",
                  "TWITCHCHATROOMSTATE", "TWITCHCHATLEAVE"]
    evt_types = ["TWITCHCHATMESSAGE"]

    def __init__(self, loop, bot_user, oauth):
        self.notifications = []
        self.channels = set()
        self.observer = Observer(bot_user, oauth)
        self.observer.start()
        self.loop = loop

        self.chat_queue = asyncio.Queue(maxsize=100, loop=loop)
        self.alert_queue = asyncio.Queue(maxsize=100, loop=loop)
        self.observer.subscribe(self.handle_event)

    def subscribe(self, channel):
        logger.info(f"Joining channel: {channel}")
        self.observer.join_channel(channel)
        self.channels.add(channel)

    def unsubscribe(self, channel):
        logger.info(f"Leaving channel: {channel}")
        self.observer.leave_channel(channel)
        if channel not in self.channels:
            logger.warn(f"Subscribing from channel not subbed: {channel}")
            logging.debug(traceback.format_stack())
        else:
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
                if evt.message.startswith("!"):
                    res = twitch.handle_command(evt)
                    if res:
                        self.send_message(res.message, evt.channel)
            except Exception as e:
                logger.warn(f"Error processing command ({e})")

            try:
                self.add_task(self.chat_queue.put(evt))
            except asyncio.QueueFull:
                logger.error("Alerts queue full, discarding alert")
            return

        if evt.type in self.evt_filter:
            return

        if evt.type == "TWITCHCHATUSERNOTICE":
            msg_id = evt.tags['msg-id']
            if msg_id == "charity":
                logger.info("Chraity stuff")
            elif msg_id == "sub":
                evt.type = "SUB"
            elif msg_id == "resub":
                evt.type = "SUB"
            elif msg_id == "raid":
                logger.info(f"RAID {evt}")
                evt.type = "RAID"
            elif msg_id == "host":
                evt.type = "HOST"
                logger.info(f"HOST {evt}")
            else:
                logger.info(evt.type)
            try:
                self.add_task(self.alert_queue.put(evt))
            except asyncio.QueueFull:
                logger.error("Alerts queue full, discarding alert")
        elif evt.type == "RECONNECT":
            logger.warn("Twitch chat is going down")
            evt = {
                "message": "Twitch chat is going down"
            }
        elif evt.type == "HOSTTARGET":
            if re.search(r"HOSTTARGET\s#\w+\s:-", evt.message):
                # TODO: Store channels hosting
                evt['message'] = "Stopped hosting"
            else:
                channel = re.search(r"HOSTTARGET\s#\w+\s(\w+)\s", evt.message).group(1)
                evt['message'] = f"Hosting {channel}"
            logger.info(evt['message'])
            self.add_task(self.chat_queue.put(evt))
        elif evt.type == "CLEARMSG":
            self.add_task(self.alert_queue.put(evt))

            

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