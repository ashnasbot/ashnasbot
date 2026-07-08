import asyncio
import random

from ._framework import *  # noqa
from ashnasbot import llm
from ashnasbot.llm import generate_chat_message, preload_model, chat_filter, SYSTEM_PROMPT  # noqa

COMMANDS = {}


@cmd("chat")
async def chat_cmd(event, *args):
    trigger = " ".join(args) if args else None

    msg = ""
    for _ in range(3):
        # The LLM call blocks (requests + pacing sleep) — keep it off the event loop
        msg = await asyncio.to_thread(
            generate_chat_message, trigger=trigger, channel=event.get("channel"))
        if msg:
            break

    if not msg:
        return

    event["message"] = msg.replace('\r\n', ' ')
    return event


@cmd("go")
def go_cmd(event, what="King", *args):
    event["message"] = f"Go {random.sample(VERBS, 1)[0]} the {what}"
    event["tags"]["pokey-say"] = True
    return event


@cmd("commands")
def commands_cmd(event, *args):
    cmds = {k: c for k, c in COMMANDS.items() if c[0]}
    event["message"] = ", ".join(sorted(cmds.keys()))
    return event
