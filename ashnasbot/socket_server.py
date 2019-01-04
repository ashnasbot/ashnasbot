import asyncio
import json
import websockets
from queue import Empty
from threading import Thread

from . import twitch
from . import av

class SocketServer(Thread):

    def __init__(self, chatbot, twitch_client):
        self.chatbot = chatbot
        self.http_client = twitch_client
        self.loop = None
        Thread.__init__(self)
        self._event_queue = None

    async def chat(self, websocket):
        try:
            while True:
                # Ping to minimise messages being thrown away
                try:
                    await websocket.ping()
                except asyncio.CancelledError:
                    pass
                if websocket.closed:
                    return
                events = self.chatbot.get_chat_messages()
                if not events: 
                    await asyncio.sleep(0.2)
                    continue

                for event in events:
                    content = twitch.handle_message(event)
                    if content:
                        await websocket.send(json.dumps(content))
        except Exception as e:
            print("Failed to get chat:", e)

    async def chat_alerts(self):
        while True:
            events = self.chatbot.get_chat_alerts()
            if not events: 
                await asyncio.sleep(3)
                continue

            for event in events:
                content = twitch.handle_message(event)
                if content:
                    await self._event_queue.put(content)

    async def heartbeat(self, websocket):
        try:
            while True:
                await asyncio.sleep(20)
                if websocket.closed:
                    return
                await websocket.ping()
        except asyncio.CancelledError:
            pass


    async def followers(self):
        while True:
            followers = self.http_client.get_new_followers()
            if not followers: 
                await asyncio.sleep(80)
                continue

            for nickname in followers:
                evt_msg = {
                    'nickname': nickname,
                    'type' : "FOLLOW"
                }

                await self._event_queue.put(evt_msg)
            # Don't spam api
            await asyncio.sleep(80)

    async def alerts(self, websocket):
        while True:
            event = await self._event_queue.get()
            if event is None:
                print("No more alerts")
                return
            if event['type'] == "FOLLOW":
                av.play_sound("Mana_got_item")
            if event['type'] == "SUB":
                av.play_sound("Super_Nintendo_Chalmers")

            print(event)

            await websocket.send(json.dumps(event))

            self._event_queue.task_done()
            await asyncio.sleep(30)


    async def handle_connect(self, websocket, path):
        try:
            command = await websocket.recv()
        except:
            return

        commands = command.split(",")
        tasks = []
        if "chat" in commands:
            tasks.append(asyncio.create_task(self.chat(websocket)))
        if "alert" in commands:
            tasks.append(asyncio.create_task(self.chat_alerts()))
            tasks.append(asyncio.create_task(self.followers()))
            tasks.append(asyncio.create_task(self.alerts(websocket)))
        if not tasks:
            return
        tasks.append(asyncio.create_task(self.heartbeat(websocket)))

        print("Socket client Join:", command)
        done = await asyncio.gather(*tasks)
        print("Socket client Leave:", command)


    def run(self):
        print("Starting socket server")
        self.loop = asyncio.new_event_loop()
        self._event_queue = asyncio.Queue(loop=self.loop)
        asyncio.set_event_loop(self.loop)
        self.loop.set_debug(enabled=True)
        start_server = websockets.serve(self.handle_connect, 'localhost', 8765)

        self.loop.run_until_complete(start_server)
        self.loop.run_forever()
