#!/usr/bin/env python3
import logging
import os.path
import shutil
import signal
import sys


def patch_crypto():
    # This is needed to help pyinstaller find the right backend
    from cryptography.hazmat import backends
    from cryptography.hazmat.backends.openssl.backend import backend as be_cc
    backends._available_backends_list = [be_cc]


def copy_resources():
    # pylint: disable=maybe-no-member
    if not hasattr(sys, "_MEIPASS") or not getattr(sys, 'frozen', False):
        return

    src_dir = os.path.join(sys._MEIPASS, "public")
    tgt_dir = os.path.join(os.path.dirname(sys.executable), "public")
    src_cfg = os.path.join(sys._MEIPASS, "example_config.json")
    tgt_cfg = os.path.join(os.path.dirname(sys.executable), "config.json")

    print("Creating web directories")
    shutil.copytree(src_dir, tgt_dir, dirs_exist_ok=True)
    if not os.path.isfile(tgt_cfg):
        print("Creating config.json")
        print(src_cfg, tgt_cfg)
        shutil.copy(src_cfg, tgt_cfg)


if __name__ == '__main__':
    copy_resources()

    # set up logging to file and screen
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    patch_crypto()

    console = logging.StreamHandler()
    formatter = logging.Formatter('%(name)-32s: %(levelname)-7s %(message)s')
    console.setLevel(logging.INFO)
    console.setFormatter(formatter)
    root_logger.addHandler(console)

    logfile = logging.FileHandler('debug.log', 'w', 'utf-8')
    logfile.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s %(name)-32s %(levelname)-7s %(message)s', "%H:%M:%S")
    logfile.setFormatter(formatter)
    root_logger.addHandler(logfile)

    # These must only be imported after the resources are in place
    # ...and post logging config
    from ashnasbot import socket_server
    from ashnasbot import config

    logging.info("Loading configuration")
    cfg = config.Config()
    try:
        lvl = cfg["log_level"].upper()
        log_level = getattr(logging, lvl)
        logging.info("Log level set to: %s", lvl)
    except Exception:
        logging.info("Log level not set, defaulting to INFO")
        log_level = logging.INFO

    console.setLevel(log_level)

    socket_thread = socket_server.SocketServer()
    signal.signal(signal.SIGINT, socket_thread.stop)
    signal.signal(signal.SIGTERM, socket_thread.stop)
    # blocks forever
    socket_thread.run()
