def no_cmd(event, who, *args):
    remainder = " ".join(args)
    event["message"] = f"No {who} {remainder}"
    return event

def so_cmd(event, who, *args):
    event["message"] = f"Shoutout to {who} - they are a good egg <3"
    return event