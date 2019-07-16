import random

def no_cmd(event, who, *args):
    remainder = " ".join(args)
    event["message"] = f"No {who} {remainder}"
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
    event["message"] = f"praise {praise} - {ending.format(praise=message)}"
    return event
