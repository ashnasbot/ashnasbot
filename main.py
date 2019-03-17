#!/usr/bin/env python3
import argparse
import time
import threading
import json
import queue
import asyncio
import signal
import os

from http.server import HTTPServer

from ashnasbot.server import Server
from ashnasbot.chat_bot import ChatBot
from ashnasbot import socket_server
from ashnasbot.twitch_client import TwitchClient


HOST_NAME = '0.0.0.0'

if __name__ == '__main__':
    with open('config.json') as f:
        config = json.load(f)

    #httpd = HTTPServer((HOST_NAME, config["port"]), Server)
    #httpd.chat_queue = queue.Queue()
    chat = ChatBot(config["channel"])
    http = TwitchClient(config["client_id"], config["channel"])
    #httpd_thread = threading.Thread(target = httpd.serve_forever)
    socket_thread = socket_server.SocketServer(chat, http)
    #httpd_thread.start()
    socket_thread.start()

    def sighandler(signum, frame):
        print("SIGNAL: ", signum)
        chat.stop()
        #httpd.shutdown()

    signal.signal(signal.SIGINT, sighandler)

    try:
        threading.Event().wait()
    except Exception as e:
        print(e)

    #httpd_thread.join()
    socket_thread.join()
