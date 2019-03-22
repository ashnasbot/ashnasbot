#!/usr/bin/env python3
import signal

from ashnasbot import socket_server

if __name__ == '__main__':
    socket_thread = socket_server.SocketServer()

    def sighandler(signum, frame):
        print("SIGNAL: ", signum)
        socket_thread.shutdown()

    signal.signal(signal.SIGINT, sighandler)

    # blocks forever
    socket_thread.start()

    socket_thread.join()
