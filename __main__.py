#!/usr/bin/env python3
import logging
import signal

# TODO: Why?
# pylint: disable=import-error, no-name-in-module
from ashnasbot import socket_server
from ashnasbot import config


if __name__ == '__main__':
    cfg = config.Config()
    try:
        lvl = cfg["log_level"].upper()
        log_level = getattr(logging, lvl)
        print("Log level set to:", lvl)
    except:
        print("Log level not set, defaulting to INFO")
        log_level = logging.INFO
    # set up logging to file and screen
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    console = logging.StreamHandler()
    console.setLevel(log_level)
    formatter = logging.Formatter('%(name)-30s: %(levelname)-6s %(message)s')
    console.setFormatter(formatter)
    root_logger.addHandler(console)

    logfile = logging.FileHandler('debug.log', 'w', 'utf-8')
    logfile.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s %(name)-30s %(levelname)-6s %(message)s', "%H:%M:%S")
    logfile.setFormatter(formatter)
    root_logger.addHandler(logfile)

    socket_thread = socket_server.SocketServer()

    def sighandler(signum, frame):
        logging.info(f"SIGNAL: {signum}")
        socket_thread.shutdown()

    signal.signal(signal.SIGINT, sighandler)

    # blocks forever
    socket_thread.start()

    socket_thread.join()
