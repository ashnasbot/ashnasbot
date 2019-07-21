#!/usr/bin/env python3
import logging
import signal

from ashnasbot import socket_server
from ashnasbot import config

if __name__ == '__main__':
    config = config.Config()
    try:
        lvl = config["log_level"].upper()
        log_level = getattr(logging, lvl)
        print("Log level set to:", lvl)
    except:
        print("Log level not set, defaulting to INFO")
        log_level = logging.INFO
    logging.basicConfig(level=log_level)
    socket_thread = socket_server.SocketServer()

    def sighandler(signum, frame):
        logging.info(f"SIGNAL: {signum}")
        socket_thread.shutdown()

    signal.signal(signal.SIGINT, sighandler)

    # blocks forever
    socket_thread.start()

    socket_thread.join()
