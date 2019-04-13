import logging
import time
import functools
from threading import Thread, current_thread, Event
from concurrent.futures import Future

import asyncio

from twitchobserver import Observer

logger = logging.getLogger(__name__)

class ChatBot():
    evt_filter = ["TWITCHCHATJOIN", "TWITCHCHATMODE", "TWITCHCHATMESSAGE",
                  "TWITCHCHATCOMMAND", "TWITCHCHATUSERSTATE",
                  "TWITCHCHATROOMSTATE", "TWITCHCHATLEAVE"]
    evt_types = ["TWITCHCHATMESSAGE"]

    def __init__(self, loop, channel, bot_user, oauth):
        self.notifications = []
        self.channel = channel
        self.observer = Observer(bot_user, oauth)
        self.observer.start()
        self.observer.join_channel(self.channel)
        self.loop = loop

        self.chat_queue = asyncio.Queue(maxsize=100, loop=loop)
        self.alert_queue = asyncio.Queue(maxsize=100, loop=loop)
        self.observer.subscribe(self.handle_event)
        logger.info(f"Joining channel: {channel}")

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

    def close(self):
        logger.info(f"closing chat {self.channel}")
        self.observer.leave_channel(self.channel)