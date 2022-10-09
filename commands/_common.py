import random

from ._framework import *  # noqa

try:
    from aitextgen import aitextgen
except ImportError:
    logger.warn("Failed to import aitextgen, text generation unavailable")

# TODO: Per channel CHATMODEL?
# TODO: Training repo
# TODO: Commands API (i.e. get stream info, etc)
# TODO: PRIV level on COMMANDS structure
CHATMODEL = None


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


def go_cmd(event, what="King", *args):
    if event["priv"] < PRIV.COMMON:
        return

    event["message"] = f"Go {random.sample(VERBS, 1)[0]} the {what}"

    return event
