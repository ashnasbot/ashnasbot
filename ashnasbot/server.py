from http.server import BaseHTTPRequestHandler
import os
from pathlib import Path

from .requestHandler import CommandHandler
from .requestHandler import BadRequestHandler
from .requestHandler import StaticHandler


routes = {
  "/api/chat" : "chat"
}


class Server(BaseHTTPRequestHandler):
    def setup(self):
        BaseHTTPRequestHandler.setup(self)
        self.request.settimeout(3)

    def do_HEAD(self):
        return

    def do_GET(self):
        split_path = os.path.splitext(self.path)
        request_extension = split_path[1]

        # if request_extension is "" or request_extension is ".html":
        if not request_extension:
            if self.path in routes:
                handler = CommandHandler(self.server)
                handler.find(routes[self.path])
                # Don't cache commands!
                # self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                # self.send_header("Pragma", "no-cache")
                # self.send_header("Expires", "0")
            else:
                handler = BadRequestHandler(self.server)
        elif request_extension is ".py":
            handler = BadRequestHandler(self.server)
        else:
            handler = StaticHandler(self.server)
            handler.find(self.path)
 
        self.respond({
            'handler': handler
        })

    def handle_http(self, handler):
        status_code = handler.get_status()
        self.send_response(status_code)

        if status_code in [200, 204]:
            content = handler.contents()
            self.send_header('Content-type', handler.get_content_type() +
                    "; charset=utf-8")
        else:
            content = "404 Not Found"
        
        self.end_headers()

        if isinstance( content, (bytes, bytearray) ):
            return content

        return bytes(content, 'utf-8')

    def respond(self, opts):
        response = self.handle_http(opts['handler'])
        self.wfile.write(response)
