import os
from io import StringIO
from queue import Empty
import json
import html

from . import twitch


class MockFile():
    def read(self):
        return ""
        
class RequestHandler():
    def __init__(self, server):
        self.content_type = ""
        self._contents = MockFile()
        self.file_types = {
            ".js" : "text/javascript",
            ".css" : "text/css",
            ".jpg" : "image/jpeg",
            ".png" : "image/png",
            ".html": "text/html",
            "json" : "application/json",
            "notfound" : "text/plain"
        }
        self.server=server

    def contents(self):
        return self._contents.read()

    def read(self):
        return self._contents

    def set_status(self, status):
        self.status = status

    def get_status(self):
        return self.status

    def get_content_type(self):
        return self.content_type 

    def get_type(self):
        return 'static'

    def set_content_type(self, ext):
        self.content_type = self.file_types.get(ext, "text/plain")




class CommandHandler(RequestHandler):
    def __init__(self, server):
        super().__init__(server)
        self.content_type = 'text/html'

    def chat(self):
        self.set_content_type('json')
        content = {'messages': []}
        try:
            while True:
                event = self.server.chat_queue.get(block=False)
                content['messages'].append(twitch.handle_message(event))
                self.server.chat_queue.task_done()
        except Empty:
            # No more messages
            pass
        except Exception as e:
            print("Failed to get chat:", e)

        if not content['messages']:
            self.set_status(204)
            return

        self.set_status(200)
        content_str = json.dumps(content)
        self._contents = StringIO(content_str)


    def find(self, route):
        try:
            command = getattr(self, route, None)
            if callable(command):
                command()
                return True
            else:
                print("command {} not found".format(route))
                self.set_status(404)
                return False
        except Exception as e:
            print(e)
            self.set_status(404)
            return False

class BadRequestHandler(RequestHandler):
    def __init__(self, server):
        super().__init__(None)
        self.content_type = 'text/plain'
        self.set_status(404)

class StaticHandler(RequestHandler):

    def find(self, file_path):
        # TODO: Handle ../
        split_path = os.path.splitext(file_path)
        extension = split_path[1]

        try: 
            if extension in (".jpg", ".jpeg", ".png", ".woff", ".ttf", ".woff2"):
                self._contents = open("public{}".format(file_path), 'rb')
            else:
                path = "public{}".format(file_path)
                self._contents = open(path, 'r', encoding='utf-8')

            self.set_content_type(extension)
            self.set_status(200)
            return True
        except:
            self.set_content_type('notfound')
            self.set_status(404)
            return False

