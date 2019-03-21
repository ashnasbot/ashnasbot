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


HOST_NAME = '0.0.0.0'

if __name__ == '__main__':
    with open('config.json') as f:
        config = json.load(f)

    chat = ChatBot(config["channel"], config["username"], config["oauth"])
    socket_thread = socket_server.SocketServer(chat, config["client_id"], config["channel"])

    def sighandler(signum, frame):
        print("SIGNAL: ", signum)
        socket_thread.shutdown()

    signal.signal(signal.SIGINT, sighandler)

    # blocks forever
    socket_thread.start()

    socket_thread.join()
