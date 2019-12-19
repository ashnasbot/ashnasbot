import logging
import random
import re
import uuid

import dataset

logger = logging.getLogger(__name__)

# TODO: command cooldown (per channel)

class ResponseEvent(dict):
    """Render our own msgs through the bot."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__dict__ = self
        self.nickname = "Ashnasbot"
        self.tags = {
            'display-name': 'Ashnasbot',
            'badges': [],
            'emotes': [],
            'user-id': 275857969 # TODO: not hardcode these :(
        }
        self.id = str(uuid.uuid4())
        self.type = 'TWITCHCHATMESSAGE'

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
    ret_event.tags['response'] = True
    if callable(cmd):
        ret_event = cmd(ret_event, *args)
        return ret_event

def handle_other_commands(event):
    try:
        if event._command == "PRIVMSG":
            return

        logger.debug("_command: %s", event._command)
        if event._command == "CLEARMSG":
            return {
                    'nickname': event.tags['login'],
                    'orig_message': event._params,
                    'id' : event.tags['target-msg-id'],
                    'type' : event._command
                    }
        elif event._command == "CLEARCHAT":
            #channel, nick = re.search(r"^#(\w+)\s:(\w+)$", event._params).groups()
            return {
                    'id' : event.tags['target-user-id'],
                    'type' : event._command
                    }
        elif event._command == "RECONNECT":
            ret_event = ResponseEvent()
            logger.warn("Twitch chat is going down")
            ret_event.message = "Twitch chat is going down"
            return ret_event
        elif event._command == "HOSTTARGET":
            ret_event = ResponseEvent()
            if event.message == "-":
                # TODO: Store channels hosting
                ret_event['message'] = "Stopped hosting"
            else:
                channel = re.search(r"(\w+)\s[\d-]+", event.message).group(1)
                ret_event['message'] = channel
                ret_event['type'] = "HOST"
            logger.info("Hosting: %s", ret_event['message'])
            return ret_event

    except Exception as e:
        logger.warn(e)
        return

db = dataset.connect('sqlite:///ashnasbot.db')

def no_cmd(event, who, *args):
    remainder = " ".join(args)
    event["message"] = f"No {who} {remainder}"
    return event

def bs_cmd(event, *args):
    event["message"] = f"No backseating please, we like to watch them suffer"
    return event

def so_cmd(event, who, *args):
    if event.tags['caller'] != 'Ashnas':
        return

    if who.lower() == "theadrain":
        event["message"] = f"Shoutout to {who} - they are the best egg <3"
    else:
        event["message"] = f"Shoutout to {who} - they are a good egg <3"
    return event
    
def uptime(event, *args):
    if event.tags['caller'] != 'Darkshoxx':
        return

    event["message"] = f"You're late, Darkshoxx!"
    return event

PRAISE_ENDINGS = [
    "saviour of ages!",
    "beware of false prophets",
    "P R A I S E",
    "GDPR compliant",
    "Euclidian",
    "Tubular",
    "Uninflammable",
    "Hydrate",
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
    "'cause why not?",
    "{praise} {praise} {praise}",
    "marginally above average",
    "Rock-Paper-Scissors champion of 1994",
    "accept some substitutes",
    "contains chemicals known to the State of California to ... be safe",
    "great at a barbecue",
    "tell your friends",
    "easy to clean",
    "jack of all trades",
    "'IwlIj jachjaj",
    "all transactions are final",
    "tax-deductable!",
    "likes ice-cream",
    "can't be all bad",
    "in stereo!",
    "now for only 19,99",
    "better than Baby Shark",
    "\"The best thign on the internet.\" - Abraham Lincoln"
]

CALM = [
    "Add three drops of orange blossom oil to a cup of mineral water, and spray it from an atomiser when you need to feel relaxed.",
    "Concentrate on silence. when it comes, dwell on what it sounds like. Then strive to carry that quiet with you wherever you go.",
    "Hard-working people never waste time on frivolous, fun-filled activities. Yet, for hard-working people, any time spent this way is far from wasted.",
    "As harsh as it may sound, mixing with highly stressed people will make you feel stressed. on the other hand, mixing with calm people - even for the breifest time - will leave you feeling calm.",
    "When you dwell on the sound of your breathing, when you can really feel it coming and going, peace will not be far behind.",
    "There's always a temptation to lump all your life changes into one masochistic event. Do your stress levels a favour and take on changes one at a time.",
    "The more beautiful your fruit bowl, the better stocked it is, the less likely you are to turn to stress-enhancing snack foods. Eat more fruit, you'll feel more relaxed, it's as sweet as that."
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
    table = db["channel"]
    if not table:
        table = db.create_table("channel", primary_id="channel", primary_type=db.types.text)
    try:
        data = table.find_one(channel=event["channel"])
        if data == None:
            data = {"channel": event["channel"], "deaths":0}
        DEATHS = data["deaths"]
    except:
        DEATHS = 0

    plus = " ".join(args)
    if event.tags['caller'] == 'Ashnas' or event.tags['caller'] == 'darkshoxx' or \
        event.tags['caller'] == 'TheADrain':
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
            table.upsert(data, ["channel"], ensure=True)

    times = "times"
    if DEATHS == 1:
        times = "time"
    event["message"] = f"/me Our illustrious strimmer has died {DEATHS} {times}"
    return event

def proffer_cmd(event, *args):
    proffered =  " ".join(args)
    event["message"] = f"!add {proffered}"
    return event

COMMANDS = {
    '!no': no_cmd,
    '!so': so_cmd,
    '!bs': bs_cmd,
    '!backseat': bs_cmd,
    '!praise': praise_cmd,
    '!calm': calm_cmd,
    '!deaths': death_cmd,
    '!uptime': uptime,
    '!proffer': proffer_cmd
}
