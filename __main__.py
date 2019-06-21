#!/usr/bin/env python3
import logging
import signal

from ashnasbot import socket_server

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    socket_thread = socket_server.SocketServer()

    def sighandler(signum, frame):
        logging.info(f"SIGNAL: {signum}")
        socket_thread.shutdown()

    signal.signal(signal.SIGINT, sighandler)

    # blocks forever
    socket_thread.start()

    socket_thread.join()
