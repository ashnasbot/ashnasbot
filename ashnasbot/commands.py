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
    "healer of leopards"
]

def praise_cmd(event, praise, *args):
    ending = random.sample(PRAISE_ENDINGS, 1)[0]
    event["message"] = f"praise {praise} - {ending}"
    return event