from importlib import import_module
import logging
import sys
import typing

logger = logging.getLogger(__name__)

REDEMPTIONS: typing.Dict[str, typing.Callable] = {}


def load_redemptions(channel, command):
    global REDEMPTIONS
    res = None
    try:
        if channel not in REDEMPTIONS:
            mod = []
            modstr = f'commands.{channel}'
            if modstr in sys.modules:
                mod = sys.modules[modstr]
            else:
                logger.debug("Importing redemptions for %s", channel)
                # TODO: sanitise this!
                mod = import_module('commands.' + channel)
                logger.info("Imported redemptions for %s", channel)
                mod.logger = logger

            if "REDEMPTIONS" in mod.__dict__.keys():
                REDEMPTIONS[channel] = mod.REDEMPTIONS
            else:
                return

        if command in REDEMPTIONS[channel]:
            res = REDEMPTIONS[channel][command]
    except ImportError:
        # Module doesn't exist, all good
        pass
    except Exception as e:
        logger.warn(e)
    finally:
        return res


def handle_channel_redemption(event):
    # TODO: more robust exception handling / bad data handling here
    #       this function trusts the handlers to be in a good format
    etags = event.tags
    raw_msg = event.message
    logger.debug(f"{etags['display-name']} REDEMPTION: {raw_msg}")
    args = raw_msg.split(" ")
    title = event.tags["title"]
    func = load_redemptions(event.channel, title)
    if not func:
        return

    if callable(func[1]):
        try:
            func[1](event, *args)
        except Exception as e:
            logger.warn(e)
            return
