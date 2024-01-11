import random
import string

from transformers import AutoTokenizer, AutoModelForSeq2SeqLM

from ._framework import *  # noqa

aitextgen = None
try:
    from aitextgen import aitextgen
    import transformers
    transformers.logging.set_verbosity_error()
    transformers.logging.disable_propagation()
except ImportError as e:
    print(e)
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
    if msg == " ":
        return False

    return True


def load_textgen():
    global CHATMODEL
    if not aitextgen:
        return

    try:
        logger.info("Loading chat textgen")
        # CHATMODEL = aitextgen(model_folder="trained_model")
        CHATMODEL = aitextgen("microsoft/DialoGPT-small", to_gpu=True)
        logger.info("Textgen available - chatbot capable")
    except Exception:
        CHATMODEL = False
        logger.info("Textgen NOT available - not chatbot capable")


def generate_text(prompt=None):
    msg = ""
    if not prompt:
        prompt = ""
    if CHATMODEL:
        eos_token = CHATMODEL.tokenizer.eos_token_id
        msg = CHATMODEL.generate_one(temperature=1.4, prompt=prompt, min_new_tokens=12,
                                     eos_token_id=eos_token).lstrip(string.punctuation)
        if not chat_filter(prompt, msg):
            msg = ""

    return msg


@cmd("chat")
def chat_cmd(event, *args):

    prompt = None
    msg = ""
    if args:
        prompt = [" ".join(args)]
    if not prompt:
        prompt = []

    # Try a few times to generate a text
    for _ in range(10):
        #msg = generate_text(prompt)
        msg = generate_chat_message(event, prompt)
        if msg:
            break

    if "\r\n" in msg:
        event["message"] = msg.replace('\r\n', ' ')
    else:
        event["message"] = msg

    return event


@cmd("go")
def go_cmd(event, what="King", *args):
    event["message"] = f"Go {random.sample(VERBS, 1)[0]} the {what}"

    return event


def generate_chat_message(event, dialog=None):
    if dialog is None:
        dialog = []

    tokenizer = AutoTokenizer.from_pretrained("microsoft/GODEL-v1_1-base-seq2seq")
    model = AutoModelForSeq2SeqLM.from_pretrained("microsoft/GODEL-v1_1-base-seq2seq")

    def generate(instruction, knowledge, dialog):
        if knowledge != '':
            knowledge = '[KNOWLEDGE] ' + knowledge
        dialog = ' EOS '.join(dialog)
        query = f"{instruction} [CONTEXT] {dialog} {knowledge}"
        input_ids = tokenizer(f"{query}", return_tensors="pt").input_ids
        outputs = model.generate(input_ids, max_length=128, min_length=8, top_p=0.9, do_sample=True)
        output = tokenizer.decode(outputs[0], skip_special_tokens=True)
        return output

    # Instruction for a chitchat task
    instruction = 'Instruction: You are AshnasBot. You are a chatter in Twitch chat. Roast the streamer. Keep conversation about games. The game is Final Fantasy Tactics Advance.'
    # Leave the knowldge empty
    knowledge = ''
    response = generate(instruction, knowledge, dialog)
    event["message"] = response
    return response
