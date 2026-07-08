from importlib import import_module
import logging
import re
import sys
import typing

logger = logging.getLogger(__name__)

REDEMPTIONS: typing.Dict[str, typing.Callable] = {}

# Channel names come from external input and are used as module names — keep them tame.
_CHANNEL_MODULE_RE = re.compile(r'^[a-z0-9_]+$')


def load_redemptions(channel, command):
    res = None
    try:
        if channel not in REDEMPTIONS:
            if not _CHANNEL_MODULE_RE.match(channel or ""):
                logger.warning("Refusing to load redemptions for channel %r", channel)
                return None
            modstr = f'commands.{channel}'
            if modstr in sys.modules:
                mod = sys.modules[modstr]
            else:
                logger.debug("Importing redemptions for %s", channel)
                mod = import_module(modstr)
                logger.info("Imported redemptions for %s", channel)
                mod.logger = logger

            if "REDEMPTIONS" in mod.__dict__:
                REDEMPTIONS[channel] = mod.REDEMPTIONS
            else:
                REDEMPTIONS[channel] = {}

        if command in REDEMPTIONS[channel]:
            res = REDEMPTIONS[channel][command]
    except ImportError:
        # Module doesn't exist, all good — cache that so we don't retry per event
        REDEMPTIONS[channel] = {}
    except Exception:
        logger.exception("Failed to load redemptions for %s", channel)
    return res


def handle_channel_redemption(event):
    etags = event.tags
    raw_msg = event.message
    logger.debug(f"{etags.get('display-name', '?')} REDEMPTION: {raw_msg}")
    args = raw_msg.split(" ")
    title = event.tags["title"]
    func = load_redemptions(event.channel, title)
    if not func:
        return

    if callable(func[1]):
        try:
            func[1](event, *args)
        except Exception:
            logger.exception("Redemption handler '%s' failed", title)
            return
