from enum import Enum, auto
import json
import logging
from pathlib import Path
import random
import time
import uuid

from ashnasbot.twitch.data.verbs import VERBS

try:
    from aitextgen import aitextgen
except ImportError:
    logging.warn("Failed to import aitextgen, text generation unavailable")
    pass

from ashnasbot.twitch.data import OutputMessage

from . import db
from . import pokedex

from .. import config

logger = logging.getLogger(__name__)
logging.getLogger("aitextgen").setLevel(logging.WARN)

GAMEINFO = ""
CHATMODEL = None

if Path("gameinfo.txt").is_file():
    with open("gameinfo.txt") as f:
        GAMEINFO = f.readline()
# TODO: command cooldown (per channel)


class BannedException(Exception):
    def __init__(self, channel):
        self.channel = channel


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
    logger.debug(f"{etags['display-name']} COMMAND: {raw_msg}")
    args = raw_msg.split(" ")
    command = args.pop(0).lower()
    cmd = COMMANDS.get(command, None)
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
            'user-type': event.tags['user-type']
        },
        "extra": ['quoted'],
        "priv": PRIV.COMMON,
        "channel": event.channel
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
            del ret_event["priv"]
            logger.debug("COMMANDRESPONSE: %s", ret_event)
            return ret_event
        except Exception:
            return


def goaway_cmd(event, *args):
    if event["priv"] < PRIV.MOD:
        event["message"] = "Only a mod or the broadcaster can remove me"
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
    event["message"] = """Wrong game! this is Final Fantasy,
                          but the mantras are here: https://pad.riseup.net/p/GUZZZVN-xPDnUJv-pEzM-keep"""
    return event


def approve_cmd(event, *args):
    event["message"] = "https://clips.twitch.tv/TrustworthyFaintFalconRlyTho"
    return event


def win_cmd(event, *args):
    val = random.randint(30, 2000)
    caller = event["tags"]['caller']
    if random.randint(1, 10) == 1:
        event["message"] = f"{caller} looses"
    else:
        event["message"] = f"{caller} wins {val} points"
    return event


def save_cmd(event, *args):
    if random.randint(1, 10) == 1:
        event["message"] = "But did you Dave?"
    else:
        event["message"] = "But did you save?"
    return event


def drink_cmd(event, *args):
    event["message"] = "Every time a character could have explained something but instead says 'nothing', we take a drink."
    return event


def hello_cmd(event, *args):
    who = event["tags"]['caller']
    event["message"] = who
    return event


def bs_cmd(event, *args):
    event["message"] = """We're experiencing this game together for the first time,
                          please don't spoil it if you already know."""
    return event


def so_cmd(event, who, *args):
    if event["priv"] < PRIV.VIP:
        return

    if who.lower() == "theadrain":
        event["message"] = f"Shoutout to {who} at https://twitch.tv/{who.lower()} - they are the best egg <3"
    else:
        event["message"] = f"Shoutout to {who} at https://twitch.tv/{who.lower()} - they are a good egg <3"
    return event


def go_cmd(event, what="King", *args):
    if event["priv"] < PRIV.COMMON:
        return

    event["message"] = f"Go {random.sample(VERBS, 1)[0]} the {what}"

    return event


def uptime(event, who, *args):
    if who.lower() != 'darkshoxx':
        return event

    event["message"] = "You're late, darkshoxx!"
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
    if event["priv"] < PRIV.VIP:
        return
    event["message"] = "This isn't Pokémon"
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
        event["message"] = ""

    return event


def poke_info_cmd(event, *args):
    event["message"] = """Using a Super Gameboy 2 and a Link-Cable to Internet adaptor,
                          we're getting 151 Pokemon the original way"""
    return event


def uncatch_pokemon_cmd(event, num, *args):
    if event["priv"] < PRIV.VIP:
        return

    pokedex.player_pokedex_catch(event["channel"], num, False)


def red_cmd(event, *args):
    event["message"] = "twitch.tv/theadrain is playing Red"
    return event


def blue_cmd(event, *args):
    event["message"] = "yes, it is blue"
    return event


def green_cmd(event, *args):
    event["message"] = "Look Dorothy, it's green"
    return event


PRAISE_ENDINGS = [
    "saviour of ages!",
    "beware of false prophets",
    "P R A I S E",
    "GDPR compliant",
    "Euclidian",
    "Hyperspectral",
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
    "available in all good toystores",
    "58 varieties",
    "banned in most states",
    "dummy thicc",
    "not just a lot of hot air",
    "it's super effective",
    "Ironmon champion"
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
    if event["priv"] < PRIV.VIP:
        return

    if not db.exists("channel"):
        db.create("channel", primary="channel")
    try:
        data = db.find("channel", channel=event["channel"])
        if data is None:
            data = {"channel": event["channel"], "deaths": 0}
        DEATHS = data["deaths"]
    except Exception:
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
        logger.info(f"Updated deaths counter: {data}")
        db.update("channel", data, ["channel"])

    times = "times"
    if DEATHS == 1:
        times = "time"
    event["message"] = f"/me Our illustrious strimmer has died {DEATHS} {times}"
    return event


def proffer_cmd(event, *args):
    proffered = " ".join(args)
    event["message"] = f"!add {proffered}"
    return event


def discord_cmd(event, *args):
    event["message"] = "Ashnas has one too! https://discord.gg/2xR2fxr"
    return event


def chat_cmd(event, *args):
    global CHATMODEL
    prompt = ""
    if args:
        prompt = " ".join(args)

    if CHATMODEL is None:
        if not aitextgen:
            return

        try:
            logger.info("Loading chat textgen")
            # TODO: test model='gpt2-medium'
            CHATMODEL = aitextgen(model_folder="trained_model",
                                  tokenizer_file="aitextgen.tokenizer.json")
            logger.info("Textgen available - chatbot capable")
        except Exception:
            CHATMODEL = False
            logger.info("Textgen NOT available - not chatbot capable")

    if CHATMODEL:
        # Try a few times to generate a text, but not just the input
        for _ in range(10):
            msg = CHATMODEL.generate_one(prompt=prompt, top_k=50, repetition_penalty=1.01,
                                         top_p=0.95, min_length=3, max_length=100)
            if msg == prompt:
                continue
            break

        # Failed to come up with anything original, just chat randomly
        if msg == prompt:
            msg = CHATMODEL.generate_one(prompt='', top_k=50, repetition_penalty=1.01,
                                         top_p=0.95, min_length=3, max_length=100)

        if "\r\n" in msg:
            event["message"] = msg.replace('\r\n', ' ')
        else:
            event["message"] = msg
    else:
        event["message"] = "durr"
    return event


def chat_how_cmd(event, *args):
    event["message"] = "GPT-2 powered by https://docs.aitextgen.io and recent vod chat."
    return event


def break_cmd(event, *args):
    event["message"] = f"While {event['channel']} is away, get up and have a stretch, make a drink or have a snack, we'll be back shortly!"
    return event


def commands_cmd(event, *args):
    cmds = {k: c for k, c in COMMANDS.items() if c[0]}
    event["message"] = ", ".join(cmds.keys())
    return event


def good_cmd(event, *args):
    event["message"] = ":D"
    return event


def bad_cmd(event, *args):
    event["message"] = ":("
    return event


COMMANDS = {
    # Command          Show   Func
    '!goawayashnasbot': (0, goaway_cmd),
    '!no':              (1, no_cmd),
    '!so':              (1, so_cmd),
    '!go':              (1, go_cmd),
    '!bs':              (0, bs_cmd),
    '!dq':              (0, discord_cmd),
    '!discord':         (1, discord_cmd),
    '!ashnasbot':       (1, hello_cmd),
    '!backseat':        (1, bs_cmd),
    '!praise':          (1, praise_cmd),
    '!calm':            (1, calm_cmd),
    '!deaths':          (1, death_cmd),
    '!uptime':          (0, uptime),
    '!chat':            (1, chat_cmd),
    '!chat_how':        (1, chat_how_cmd),
    '!proffer':         (0, proffer_cmd),
    '!commands':        (1, commands_cmd),
    '!breaktime':       (1, break_cmd),
    '!good_bot':        (0, good_cmd),
    '!bad_bot':         (0, bad_cmd),
    # Poke
    '!pokedex':         (0, pokedex_cmd),
    '!catch':           (0, catch_pokemon_cmd),
    '!uncatch':         (0, uncatch_pokemon_cmd),
    '!151':             (0, poke_info_cmd),
    '!red':             (0, red_cmd),
    '!blue':            (0, blue_cmd),
    '!green':           (0, green_cmd),
    # meme
    '!gameinfo':        (1, gameinfo_cmd),
    '!mantras':         (0, mantras_cmd),
    '!approve':         (1, approve_cmd),
    '!beta':            (1, beta_cmd),
    '!win':             (1, win_cmd),
    '!save':            (1, save_cmd),
    '!drink':           (1, drink_cmd),
}
