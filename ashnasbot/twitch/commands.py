from importlib import import_module
import logging
import sys
import typing

from ashnasbot.twitch.data import OutputMessage
from commands._framework import PRIV
import commands._common as common  # noqa used elsewhere, imported here as a helper

from .. import config

logger = logging.getLogger(__name__)
logging.getLogger("aitextgen").setLevel(logging.WARN)

# TODO: command cooldown (per channel)
COMMANDS: typing.Dict[str, typing.Callable] = {}


class BannedException(Exception):
    def __init__(self, channel):
        self.channel = channel


def load_command(channel, command):
    global COMMANDS
    res = None
    try:
        if channel not in COMMANDS:
            mod = []
            if 'commands.ashnas' in sys.modules:
                mod = sys.modules['commands.ashnas']
            else:
                logger.debug("Importing commands for %s", channel)
                # TODO: sanitise this!
                mod = import_module('commands.' + channel)
                logger.info("Imported commands for %s", channel)
                mod.logger = logger

            if "COMMANDS" in mod.__dict__.keys():
                mod.COMMANDS.update(common.COMMANDS)
                COMMANDS[channel] = mod.COMMANDS
            else:
                return

        if command in COMMANDS[channel]:
            res = COMMANDS[channel][command]
    except ImportError:
        # Module doesn't exist, all good
        pass
    except Exception as e:
        logger.warn(e)
    finally:
        if not res:
            if command in GLOBAL_COMMANDS:
                return GLOBAL_COMMANDS[command]
        return res


def handle_command(event, auth):
    # TODO: more robust exception handling / bad data handling here
    #       this function trusts the commands to be in a good format
    etags = event.tags
    raw_msg = event.message
    logger.debug(f"{etags['display-name']} COMMAND: {raw_msg}")
    args = raw_msg.split(" ")
    command = args.pop(0).lower()
    cmd = load_command(event.channel, command)
    if not cmd:
        return

    cfg = config.Config()
    name = cfg['displayname'] if 'displayname' in cfg else cfg['username']

    ret_event = OutputMessage({
        "type": "TWITCHCHATMESSAGE",
        "nickname": "Ashnasbot",
        "tags": {
            'display-name': name,
            'user-id': cfg["user_id"],
            'caller': event.tags['display-name'],
            'user-type': event.tags['user-type'],
            'badges': []
        },
        "extra": ['quoted'],
        "channel": event.channel,
        # Helper bits that are deleted on output
        "auth": auth,
        "priv": PRIV.COMMON,
        "reply": event.reply
    })

    priv_level = PRIV.COMMON
    if 'staff' in event.tags['badges']:
        priv_level = PRIV.STAFF
    elif 'broadcaster' in event.tags['badges']:
        priv_level = PRIV.OWNER
    elif 'moderator' in event.tags['badges']:
        priv_level = PRIV.MOD
    elif 'vip' in event.tags['badges']:
        priv_level = PRIV.VIP
    elif 'subscriber' in event.tags['badges']:
        priv_level = PRIV.SUB

    ret_event["priv"] = priv_level
    ret_event["tags"]['response'] = True
    if callable(cmd[1]):
        try:
            ret_event = cmd[1](ret_event, *args)
            if ret_event:
                del ret_event["priv"]
                del ret_event["auth"]
                del ret_event["reply"]
                logger.debug("COMMANDRESPONSE: %s", ret_event)
                return ret_event
        except Exception as e:
            logger.warn(e)
            return


def goaway_cmd(event, *args):
    if event["priv"] < PRIV.MOD:
        event["message"] = "Only a mod or the broadcaster can remove me"
        return event
    raise BannedException(event["channel"])


def testglobal_cmd(event, *args):
    event["message"] = "This is a successful test of the global commands system"
    return event


GLOBAL_COMMANDS = {
    # Command          Show   Func
    '!goawayashnasbot': (0, goaway_cmd),
    '!testglobal':      (0, testglobal_cmd),
}
