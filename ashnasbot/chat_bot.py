from twitchobserver import Observer
import time


class ChatBot():
    def __init__(self, channel, bot_user, oauth):
        self.notifications = []
        self.channel = channel
        self.observer = Observer(bot_user, oauth)
        self.observer.start()
        self.observer.join_channel(self.channel)
        print(f"Joining channel: {channel}")

#    def handle_event(self, event):
#        print("Twitch event", event)
#        if event.type == 'TWITCHCHATMESSAGE':
#            self.queue.put(event)
#        else:
#            print(event)

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
                    print("Chraity stuff")
                elif msg_id == "sub":
                    evt.type = "SUB"
                elif msg_id == "resub":
                    evt.type = "SUB"
                elif msg_id == "raid":
                    print("RAID", evt)
                    evt.type = "RAID"
                elif msg_id == "host":
                    evt.type = "HOST"
                    print("HOST", evt)
                else:
                    print(evt.type)
                print(msg_id, evt)
            self.notifications.append(evt)

        return [ e for e in evts
                 if e.type in evt_types]

 #       return [ e for e in self.observer.get_events()
 #               if e.type == 'TWITCHCHATMESSAGE']

    def get_chat_alerts(self):
        alerts = self.notifications.copy()
        self.notifications = []
        return alerts


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

