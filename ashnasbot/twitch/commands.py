from importlib import import_module
import inspect
import logging
import re
import sys
import typing

from ashnasbot.twitch.data import OutputMessage, EventType
from commands._framework import PRIV
import commands._common as common  # noqa used elsewhere, imported here as a helper

from .. import config

logger = logging.getLogger(__name__)

# Channel names come from external input and are used as module names — keep them tame.
_CHANNEL_MODULE_RE = re.compile(r'^[a-z0-9_]+$')

# TODO: command cooldown (per channel)
COMMANDS: typing.Dict[str, typing.Callable] = {}
REDEMPTIONS: typing.Dict[str, typing.Callable] = {}


class BannedException(Exception):
    def __init__(self, channel):
        self.channel = channel


def load_command(channel, command):
    res = None
    try:
        if channel not in COMMANDS:
            if not _CHANNEL_MODULE_RE.match(channel or ""):
                logger.warning("Refusing to load commands for channel %r", channel)
                return GLOBAL_COMMANDS.get(command)
            modstr = f'commands.{channel}'
            if modstr in sys.modules:
                mod = sys.modules[modstr]
            else:
                logger.debug("Importing commands for %s", channel)
                mod = import_module(modstr)
                logger.info("Imported commands for %s", channel)
                mod.logger = logger

            if "COMMANDS" in mod.__dict__:
                mod.COMMANDS.update(common.COMMANDS)
                COMMANDS[channel] = mod.COMMANDS
            else:
                COMMANDS[channel] = {}

        if command in COMMANDS[channel]:
            res = COMMANDS[channel][command]
    except ImportError:
        # Module doesn't exist, all good — cache that so we don't retry per message
        COMMANDS[channel] = {}
    except Exception:
        logger.exception("Failed to load commands for %s", channel)

    if not res:
        res = GLOBAL_COMMANDS.get(command)
    return res


async def handle_command(event, auth):
    etags = event.tags
    raw_msg = event.message
    logger.debug(f"{etags.get('display-name', '?')} COMMAND: {raw_msg}")
    args = raw_msg.split(" ")
    command = args.pop(0).lower()
    cmd = load_command(event.channel, command)
    if not cmd:
        return

    cfg = config.Config()
    name = cfg.get('displayname', None) or cfg.get('username', 'AshnasBot')

    ret_event = OutputMessage({
        "type": EventType.TWITCHCHATMESSAGE,
        "nickname": "Ashnasbot",
        "tags": {
            'display-name': name,
            'user-id': cfg["user_id"],
            'caller': event.tags['display-name'],
            'user-type': event.tags.get('user-type', ''),
            'badges': []
        },
        "extra": ['quoted'],
        "channel": event.channel,
        # Helper bits that are deleted on output
        "auth": auth,
        "priv": PRIV.COMMON,
        "reply": event.reply
    })

    # Resolve badge set IDs from either EventSub (_badges_raw list) or IRC (badges string).
    raw_badges = event.tags.get('_badges_raw')
    if raw_badges is not None:
        badge_ids = {b.get('set_id', '') for b in raw_badges}
    else:
        badge_str = event.tags.get('badges', '')
        badge_ids = {b.split('/')[0] for b in badge_str.split(',') if b}

    priv_level = PRIV.COMMON
    if 'staff' in badge_ids:
        priv_level = PRIV.STAFF
    elif 'broadcaster' in badge_ids:
        priv_level = PRIV.OWNER
    elif 'moderator' in badge_ids:
        priv_level = PRIV.MOD
    elif 'vip' in badge_ids:
        priv_level = PRIV.VIP
    elif 'subscriber' in badge_ids:
        priv_level = PRIV.SUB

    ret_event["priv"] = priv_level
    ret_event["tags"]['response'] = True
    if callable(cmd[1]):
        try:
            ret_event = cmd[1](ret_event, *args)
            if inspect.isawaitable(ret_event):
                ret_event = await ret_event
            if ret_event:
                for helper_key in ("priv", "auth", "reply"):
                    ret_event.pop(helper_key, None)
                logger.debug("COMMANDRESPONSE: %s", ret_event)
                return ret_event
        except BannedException:
            raise
        except Exception:
            logger.exception("Command %s failed", command)
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
