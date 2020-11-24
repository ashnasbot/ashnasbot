#!/usr/bin/env python3
import logging
import sys
import signal

from ashnasbot import socket_server
from ashnasbot import config


def patch_crypto():
    # This is needed to help pyinstaller find the right backend
    from cryptography.hazmat import backends
    from cryptography.hazmat.backends.openssl.backend import backend as be_cc
    backends._available_backends_list =[be_cc]


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
    patch_crypto()

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
    signal.signal(signal.SIGINT, socket_thread.stop)
    # blocks forever
    socket_thread.run()