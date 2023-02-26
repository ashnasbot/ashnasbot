"""Useful/required stuff to import for commands."""
from enum import Enum, auto, Flag
import functools
import logging

from ashnasbot.config import Config
from ashnasbot.twitch import db, api_client
from ashnasbot.twitch.data import create_event
from ashnasbot.twitch.data.verbs import VERBS

logger = logging.Logger('framework', logging.NOTSET)


class OrderedEnum(Enum):
    def __ge__(self, other):
        if self.__class__ is other.__class__:
            return self.value >= other.value
        return NotImplemented

    def __gt__(self, other):
        if self.__class__ is other.__class__:
            return self.value > other.value
        return NotImplemented

    def __le__(self, other):
        if self.__class__ is other.__class__:
            return self.value <= other.value
        return NotImplemented

    def __lt__(self, other):
        if self.__class__ is other.__class__:
            return self.value < other.value
        return NotImplemented


class PRIV(str, OrderedEnum):
    COMMON = auto()
    SUB = auto()
    VIP = auto()
    MOD = auto()
    OWNER = auto()
    STAFF = auto()

class VISIBILITY(Flag):
    VISIBLE = True
    NOT_VISIBLE = False


API_CLIENT = api_client.TwitchClient()


def make_message(channel, message=""):
    msg = create_event('TWITCHCHATMESSAGE', message)
    username = Config()["username"]
    msg.channel = channel
    msg.nickname = username
    msg.tags["display-name"] = username
    msg.tags["response"] = True
    return msg


async def send_message(event, message):
    msg = make_message(event["channel"], message)
    await event["reply"](msg)


def cmd(slug, priv=PRIV.COMMON, visibility=VISIBILITY.VISIBLE):
    def inner_wrapper(func):
        commands = func.__globals__['COMMANDS']
        if f"!{slug}" in commands:
            raise ValueError(f"Command {slug} already exists")

        @functools.wraps(func)
        def cmd_wrapper(event, *args, **kwargs):
            if "priv" not in event:
                event["priv"] = PRIV.COMMON
            if event["priv"] < priv:
                return

            return func(event, *args, **kwargs)

        commands[f"!{slug}"] = (visibility, cmd_wrapper)
        return cmd_wrapper
    return inner_wrapper


__all__ = ["PRIV", "VERBS", "db", "logger", "API_CLIENT", "send_message", "cmd", "VISIBILITY"]
