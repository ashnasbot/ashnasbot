import logging
import time

from twitchobserver import Observer

logger = logging.getLogger(__name__)

class ChatBot():
    def __init__(self, channel, bot_user, oauth):
        self.notifications = []
        self.channel = channel
        self.observer = Observer(bot_user, oauth)
        self.observer.start()
        self.observer.join_channel(self.channel)
        logger.info(f"Joining channel: {channel}")

#    def handle_event(self, event):
#        logger.info("Twitch event", event)
#        if event.type == 'TWITCHCHATMESSAGE':
#            self.queue.put(event)
#        else:
#            logger.info(event)

    def get_chat_messages(self, clear=True):
        evts = self.observer.get_events()
        evt_filter = ["TWITCHCHATJOIN", "TWITCHCHATMODE", "TWITCHCHATMESSAGE",
                "TWITCHCHATCOMMAND", "TWITCHCHATUSERSTATE",
                "TWITCHCHATROOMSTATE", "TWITCHCHATLEAVE"]
        evt_types = ["TWITCHCHATMESSAGE"]

        for evt in evts:
            if evt.type in evt_filter:
                continue
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
                logger.info(f"{msg_id}: {evt}")
            self.notifications.append(evt)

        new_messages = [ e for e in evts
                 if e.type in evt_types]
        for m in new_messages:
            logger.debug(m)
        return new_messages

    def get_chat_alerts(self):
        alerts = self.notifications.copy()
        self.notifications = []
        return alerts

    def close(self):
        logger.info(f"closing chat {self.channel}")
        self.observer.leave_channel(self.channel)


#    def start(self):
#        self.running = True
#        with self.observer as observer:
#            observer.join_channel(self.channel)
#
#            while self.running:
#                try:
#                    for event in observer.get_events():
#                        self.handle_event(event)
#                    time.sleep(1)
#                        
#                except KeyboardInterrupt:
#                    break
#
#            observer.leave_channel(self.channel)

#    def stop(self):
#        self.observer.leave_channel(self.channel)
#        self.running = False

