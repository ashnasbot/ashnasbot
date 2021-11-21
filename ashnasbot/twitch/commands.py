import json
import logging
import os
import random
import re
import time
import uuid

from . import db
from . import pokedex

from .. import config

logger = logging.getLogger(__name__)

# TODO: load from gameinfo.txt
GAMEINFO = "Pokémon Blue Version is a 1996 RPG developed by Game Freak for the Nintendo Game Boy"
# TODO: command cooldown (per channel)

class BannedException(Exception):
    def __init__(self, channel):
        self.channel = channel

class ResponseEvent(dict):
    """Render our own msgs through the bot."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__dict__ = self
        self.nickname = "Ashnasbot"
        cfg = config.Config()
        name = cfg['displayname'] if 'displayname' in cfg else cfg['username']
        self.tags = {
            'display-name': name,
            'badges': [],
            'emotes': [],
            'user-id': cfg["user_id"]
        }
        self.id = str(uuid.uuid4())
        self.extra = ['quoted']
        self.type = 'TWITCHCHATMESSAGE'
        self.priv = PRIV.COMMON
    

from enum import Enum, auto
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


def handle_command(event):
    etags = event.tags
    raw_msg = event.message
    logger.info(f"{etags['display-name']} COMMAND: {raw_msg}")
    args = raw_msg.split(" ")
    command = args.pop(0).lower()
    cmd = COMMANDS.get(command, None)

    ret_event = ResponseEvent()
    ret_event.channel = event.channel
    ret_event.tags['caller'] = event.tags['display-name']
    ret_event.tags['user-type'] = event.tags['user-type']

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

    ret_event.priv = priv_level
    ret_event.tags['response'] = True
    if callable(cmd):
        try:
            ret_event = cmd(ret_event, *args)
            ret_event.priv = ""
            return ret_event
        except:
            return

def handle_other_commands(event):
    try:
        if event._command == "PRIVMSG":
            return

        if event._command == "CLEARMSG":
            logger.debug("CLEAR: %s", event.tags['target-msg-id'])
            return {
                    'nickname': event.tags['login'],
                    'orig_message': event._params,
                    'id' : event.tags['target-msg-id'],
                    'type' : event._command
                    }
        elif event._command == "CLEARCHAT":
            user = event.tags.get('target-user-id', "")
            logger.debug("CLEAR: %s from %s", user, event.tags['room-id'])
            return {
                    'id' : str(uuid.uuid4()),
                    'user' : user,
                    'room': event.tags['room-id'],
                    'type' : event._command
                    }
        elif event._command == "RECONNECT":
            ret_event = ResponseEvent()
            logger.warn("Twitch chat is going down")
            ret_event['message'] = "Twitch chat is going down"
            return ret_event
        #elif event._command == "HOSTTARGET":
        #    ret_event = ResponseEvent()
        #    if event.message.startswith("- "):
        #        ret_event['message'] = "Stopped hosting"
        #    else:
        #        print(event.message)
        #        logger.debug(event.message)
        #        channel = re.search(r"(\w+)\s[\d-]+", event.message).group(1)
        #        ret_event['message'] = channel
        #        ret_event['type'] = "HOST"
        #    logger.info("HOST %s", ret_event['message'])
        #    return ret_event

    except Exception as e:
        logger.warn(e)
        return

def goaway_cmd(event, *args):
    if event.priv < PRIV.MOD:
        event["message"] = f"Only a mod or the broadcaster can remove me"
        return event
    raise BannedException(event["channel"])

def no_cmd(event, who, *args):
    remainder = " ".join(args)
    event["message"] = f"No {who} {remainder}"
    return event

def beta_cmd(event, *args):
    event["message"] = "*Ralph Wiggum voice* I'm in Beta"
    return event

def gameinfo_cmd(event, *args):
    event["message"] = GAMEINFO
    return event

def mantras_cmd(event, *args):
    event["message"] = """Wrong game! this is Final Fantasy, but the mantras are here: https://pad.riseup.net/p/GUZZZVN-xPDnUJv-pEzM-keep"""
    return event

def approve_cmd(event, *args):
    event["message"] = "https://clips.twitch.tv/TrustworthyFaintFalconRlyTho"
    return event

def win_cmd(event, *args):
    val = random.randint(30, 2000)
    caller =  event.tags['caller']
    if random.randint(1, 10) == 1:
        event["message"] = f"{caller} looses"
    else:
        event["message"] = f"{caller} wins {val} points"
    return event

def save_cmd(event, *args):
    if random.randint(1, 10) == 1:
        event["message"] = f"But did you Dave?"
    else:
        event["message"] = "But did you save?"
    return event


def hello_cmd(event, *args):
    who = event.tags['caller']
    event["message"] = who
    return event

def bs_cmd(event, *args):
    event["message"] = f"We're experiencing this game together for the first time, please don't spoil it if you already know."
    return event

def so_cmd(event, who, *args):
    if event.priv < PRIV.VIP:
        return

    if who.lower() == "theadrain":
        event["message"] = f"Shoutout to {who} at https://twitch.tv/{who.lower()} - they are the best egg <3"
    else:
        event["message"] = f"Shoutout to {who} at https://twitch.tv/{who.lower()} - they are a good egg <3"
    return event
    
def uptime(event, *args):
    if event.tags['caller'].lower() != 'darkshoxx':
        return

    event["message"] = f"You're late, darkshoxx!"
    return event

def pokedex_cmd(event, *args):
    if not args:
        player = event["channel"]
        dex = pokedex.get_player_pokedex(player)
        num = len([row for row in dex if row['caught']])
        event["message"] = f"{player} has caught {num}/151 Pokémon"

        return event

    num_or_name = args[0]
    pokemon = pokedex.get_pokemon(num_or_name)
    if pokemon:
        caughtby = json.loads(pokemon["caughtby"])
        caught_text = ""
        found_text = ""
        dex_entry = ""

        if caughtby:
            caught_text = f" - caught by {list(caughtby.keys())}"

        if "found_in" in pokemon and pokemon["found_in"]:
            found_text = f" - found in {pokemon['found_in']}"

        if "dex_entry" in pokemon and pokemon["dex_entry"]:
            dex_entry = f", {pokemon['dex_entry'][:-1]}"


        event["message"] = f'Pokémon #{pokemon["id"]} is {pokemon["name"]}{found_text}{caught_text}{dex_entry}'
    else:
        event["message"] = f"Pokémon '{num_or_name}' not found"

    return event

def catch_pokemon_cmd(event, num_or_name, *args):
    if event.priv < PRIV.VIP:
        return
    event["message"] = f"This isn't Pokémon"
    return event

    pokemon = pokedex.get_pokemon(num_or_name)

    try:
        if pokemon:
            pokedex.player_pokedex_catch(event["channel"], pokemon["id"])
            caughtby = json.loads(pokemon["caughtby"])
            caughtby[event["channel"]] = f"{time.time()}"
            pokemon["caughtby"] = json.dumps(caughtby)
            db.update("pokedex", pokemon, ["name"])
            event["message"] = f"{pokemon['name']} was caught by {event['channel']}"
        else:
            event["message"] = f"Pokemon '{num_or_name}' not found"
    except Exception as e:
        print(e)
        event["message"] = f""

    return event

def poke_info_cmd(event, *args):
    event["message"] = f"Using a Super Gameboy 2 and a Link-Cable to Internet adaptor, we're getting 151 Pokemon the original way"
    return event

def uncatch_pokemon_cmd(event, num, *args):
    if event.priv < PRIV.VIP:
        return

    pokedex.player_pokedex_catch(event["channel"], num, False)

def red_cmd(event, *args):
    event["message"] = f"twitch.tv/theadrain is playing Red"
    return event

def blue_cmd(event, *args):
    event["message"] = f"yes, it is blue"
    return event

def green_cmd(event, *args):
    event["message"] = f"Look Dorothy, it's green"
    return event


PRAISE_ENDINGS = [
    "saviour of ages!",
    "beware of false prophets",
    "P R A I S E",
    "GDPR compliant",
    "Euclidian",
    "Non-Euclidian",
    "Tubular",
    "Uninflammable",
    "Hydrate",
    "Lost but not forgotten"
    "mostly hyperbole",
    "has pictures of Spiderman",
    "turing complete",
    "undefeated",
    "gud at speeling",
    "this isn't even their final form",
    "pet friendly",
    "& Knuckles",
    "HTTP Error 418 (Teapot Error)",
    "follows the train, CJ",
    "may contain nuts",
    "Wololo.",
    "lord and saviour",
    "and also CUBE",
    "healer of leopards",
    "a good egg",
    "like and subscribe",
    "'cause why not?",
    "{praise} {praise} {praise}",
    "marginally above average",
    "Rock-Paper-Scissors champion of 1994",
    "accept some substitutes",
    "contains chemicals known to the State of California to ... be safe",
    "great at a barbecue",
    "tell your friends",
    "easy to clean",
    "ＤＥＬＵＸＥ",
    "™",
    "All rights reserved",
    "jack of all trades",
    "'IwlIj jachjaj",
    "all transactions are final",
    "tax-deductable!",
    "likes ice-cream",
    "can't be all bad",
    "in stereo!",
    "now for only 19,99",
    "better than Baby Shark",
    "\"The best thing on the internet.\" - Abraham Lincoln",
    "omnishambles!",
    "'aint afraid of no ghost",
    "12/10",
    "better than a bucket of steam",
    "can be worn as a hat",
    "available in all good toystores"
]

CALM = [
    "Add three drops of orange blossom oil to a cup of mineral water, and spray it from an atomiser when you need to feel relaxed.",
    "Concentrate on silence. when it comes, dwell on what it sounds like. Then strive to carry that quiet with you wherever you go.",
    "Hard-working people never waste time on frivolous, fun-filled activities. Yet, for hard-working people, any time spent this way is far from wasted.",
    "As harsh as it may sound, mixing with highly stressed people will make you feel stressed. on the other hand, mixing with calm people - even for the breifest time - will leave you feeling calm.",
    "When you dwell on the sound of your breathing, when you can really feel it coming and going, peace will not be far behind.",
    "There's always a temptation to lump all your life changes into one masochistic event. Do your stress levels a favour and take on changes one at a time.",
    "The more beautiful your fruit bowl, the better stocked it is, the less likely you are to turn to stress-enhancing snack foods. Eat more fruit, you'll feel more relaxed, it's as sweet as that.",
    "The most important skill in staying calm is not to lose sleep over small issues. The second most important skill is to be able to view ALL issues as small issues.",
    "Start every journey ten minutes early. Not only will you avoid the stress of haste, but if all goes well you'll have ten minutes to relax before your next engagement.",
    "Most worries are future-based. They revolve around things that, in most cases, will never happen. Concentrate on the present and the future will take care of itself.",
    "If you substitute a herbal tea such as peppermint for more stimulating drinks such as coffee and tea, your ability to be calm will be enhanced many times.",
    "If you want to trick your subconscious into helping you feel calm, simply repeat: 'Every moment I feel calmer and calmer.'"
]

def praise_cmd(event, praise, *args):
    ending = random.sample(PRAISE_ENDINGS, 1)[0]
    message = " ".join([praise, *args])
    event["message"] = f"Praise {message} - {ending.format(praise=message)}"
    return event

def calm_cmd(event, *args):
    event["message"] = random.sample(CALM, 1)[0]
    return event

def death_cmd(event, *args):
    if event.priv < PRIV.VIP:
        return

    if not db.exists("channel"):
        db.create("channel", primary="channel")
    try:
        data = db.find("channel", channel=event["channel"])
        if data == None:
            data = {"channel": event["channel"], "deaths":0}
        DEATHS = data["deaths"]
    except:
        DEATHS = 0

    plus = " ".join(args)
    update = True
    if plus == "":
        update = False
    elif plus == "++":
        DEATHS += 1
    elif plus == "--":
        DEATHS -= 1
    else:
        try:
            DEATHS = int(plus)
        except ValueError:
            update = False
            event["message"] = f"/me unknown deaths value: {plus}"
            return event

    if update:
        data["deaths"] = DEATHS
        # TODO: logger
        db.update("channel", data, ["channel"])

    times = "times"
    if DEATHS == 1:
        times = "time"
    event["message"] = f"/me Our illustrious strimmer has died {DEATHS} {times}"
    return event

def proffer_cmd(event, *args):
    proffered =  " ".join(args)
    event["message"] = f"!add {proffered}"
    return event

def discord_cmd(event, *args):
    event["message"] = "Ashnas has one too! https://discord.gg/2xR2fxr"
    return event

COMMANDS = {
    '!goawayashnasbot': goaway_cmd,
    '!no': no_cmd,
    '!so': so_cmd,
    '!bs': bs_cmd,
    '!dq': discord_cmd,
    '!discord': discord_cmd,
    '!ashnasbot': hello_cmd,
    '!backseat': bs_cmd,
    '!praise': praise_cmd,
    '!calm': calm_cmd,
    '!deaths': death_cmd,
    '!uptime': uptime,
    '!proffer': proffer_cmd,
    # Poke
    '!pokedex': pokedex_cmd,
    '!catch': catch_pokemon_cmd,
    '!uncatch': uncatch_pokemon_cmd,
    '!151': poke_info_cmd,
    '!red': red_cmd,
    '!blue': blue_cmd,
    '!green': green_cmd,
    #meme
    '!gameinfo': gameinfo_cmd,
    '!mantras': mantras_cmd,
    '!approve': approve_cmd,
    '!beta': beta_cmd,
    '!win': win_cmd,
    '!save': save_cmd,
}
