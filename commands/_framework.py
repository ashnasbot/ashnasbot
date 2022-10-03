"""Useful/required stuff to import for commands."""
from enum import Enum, auto
import logging

from ashnasbot.twitch.data.verbs import VERBS
from ashnasbot.twitch import db

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


__all__ = ["PRIV", "VERBS", "db", "logger"]
