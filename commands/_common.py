import random
import string

from ._framework import *  # noqa

try:
    from aitextgen import aitextgen
except ImportError:
    logger.warn("Failed to import aitextgen, text generation unavailable")

# TODO: Per channel CHATMODEL?
# TODO: Training repo
# TODO: Commands API (i.e. get stream info, etc)
CHATMODEL = None
COMMANDS = {}


def chat_filter(prompt: str, msg: str) -> bool:
    if msg == prompt:
        return False
    if len(msg) == len(prompt) + 1:
        return False
    if msg.startswith("/"):
        return False

    return True


@cmd("chat")
def chat_cmd(event, *args):
    global CHATMODEL
    prompt = ""
    if args:
        prompt = " ".join(args)
    if prompt == "":
        prompt = "<|endoftext|>"

    if CHATMODEL is None:
        if not aitextgen:
            return

        try:
            logger.info("Loading chat textgen")
            CHATMODEL = aitextgen(model_folder="trained_model")
            logger.info("Textgen available - chatbot capable")
        except Exception:
            CHATMODEL = False
            logger.info("Textgen NOT available - not chatbot capable")

    if CHATMODEL:
        # Try a few times to generate a text, but not just the input
        for _ in range(10):
            # msg = CHATMODEL.generate_one(prompt=prompt, top_k=50, repetition_penalty=1.01,
            #                             top_p=0.95, min_length=3, max_length=100)
            msg = CHATMODEL.generate_one(temperature=0.8, prompt=prompt, min_length=2).lstrip(string.punctuation)
            if not chat_filter(prompt, msg):
                msg = ""
                continue
            break

        # Failed to come up with anything original, just chat randomly
        while msg == "":
            msg = CHATMODEL.generate_one(temperature=0.8, prompt=prompt, min_length=2).lstrip(string.punctuation)

        if "\r\n" in msg:
            event["message"] = msg.replace('\r\n', ' ')
        else:
            event["message"] = msg
    else:
        event["message"] = "durr"
    return event


@cmd("go")
def go_cmd(event, what="King", *args):
    event["message"] = f"Go {random.sample(VERBS, 1)[0]} the {what}"

    return event
