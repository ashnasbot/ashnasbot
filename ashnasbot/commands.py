def no_cmd(who, *args):
    remainder = " ".join(args)
    return f"No {who} {remainder}"