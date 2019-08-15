import random

import dataset

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

PRAISE_ENDINGS = [
    "saviour of ages!",
    "beware of false prophets",
    "P R A I S E",
    "GDPR compliant",
    "Euclidian",
    "Tubular",
    "Uninflammable",
    "Hydrate",
    "Mostly hyperbole",
    "has pictures of Spiderman",
    "turing complete",
    "undefeated",
    "gud at speeling",
    "this isn't even their final form",
    "pet friendly",
    "& Knuckles",
    "HTTP Error 418 (Teapot Error)",
    "follows the train, CJ",
    "May contain nuts",
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
    "Better than Baby Shark"
]

def praise_cmd(event, praise, *args):
    ending = random.sample(PRAISE_ENDINGS, 1)[0]
    message = " ".join([praise, *args])
    event["message"] = f"praise {message} - {ending.format(praise=message)}"
    return event

def death_cmd(event, *args):
    table = db["channel"]
    try:
        data = table.find_one(channel=event["channel"])
        if data == None:
            data = {"channel": event["channel"], "deaths":0}
        DEATHS = data["deaths"]
    except:
        DEATHS = 0

    plus = " ".join(args)
    if event.tags['caller'] == 'Ashnas' or event.tags['caller'] == 'Darkshoxx' or \
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

