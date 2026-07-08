import logging
import random
import re
import time

import requests

from .config import Config

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are AshnasBot, a loveable and self-aware regular in this Twitch chat. "
    "You are not an assistant — never offer help, advice, or follow-up questions. "
    "React the way a warm, witty friend watching the stream would: genuine, playful, in the moment. "
    "One sentence. No questions. No 'I'. Plain text only."
)

EVENT_SYSTEM_PROMPT = (
    "You are AshnasBot, a witty Twitch chatbot. React to the channel event in one short warm phrase. "
    "First person, positive — acknowledge who it is and what they did. "
    "Be genuine and vary your responses. Plain text only, no emoji."
)

_stream_context: str | None = None


def _api_url() -> str:
    base = str(Config().get("chat_api_base", "http://framework:8892/v1"))
    return base.rstrip("/") + "/chat/completions"


def _build_prompt(dialog: list[str], trigger: str | None, thread: list | None) -> list[dict]:
    if thread:
        msgs = [{"role": role, "content": text} for role, text in thread]
        msgs.append({"role": "user", "content": trigger})
        return msgs

    if not trigger and dialog:
        trigger = dialog[-1]
        dialog = dialog[:-1]

    log = ("[CHAT LOG]\n" + "\n".join(dialog) + "\n[END LOG]\n\n") if dialog else ""
    content = f"{log}[REPLY TO]\n{trigger}\n[/REPLY TO]" if trigger else "(no recent chat)"
    return [{"role": "user", "content": content}]


def _generate(dialog, trigger=None, thread=None, system_prompt=None, max_new_tokens=500, channel=None, **sampling):
    primary = sampling.pop("model", None) or str(Config().get("chat_model", "gemma4"))
    fallback = str(Config().get("chat_model_fallback", ""))
    sampling.pop("think", None)

    base_prompt = system_prompt or SYSTEM_PROMPT
    if not system_prompt:
        if channel:
            base_prompt = base_prompt + f" You are in {channel}'s channel."
        if _stream_context:
            base_prompt = base_prompt + f" The stream is currently playing: {_stream_context}."

    messages = [{"role": "system", "content": base_prompt}]
    messages.extend(_build_prompt(dialog, trigger, thread))

    payload: dict = {
        "stream": False,
        "messages": messages,
        "temperature": sampling.get("temperature", 0.8),
        "top_p": sampling.get("top_p", 0.90),
        "max_tokens": max_new_tokens,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    if "repetition_penalty" in sampling:
        payload["frequency_penalty"] = sampling["repetition_penalty"]

    models = [primary] + ([fallback] if fallback and fallback != primary else [])
    min_delay = random.uniform(3.0, 5.0)
    t0 = time.monotonic()
    text = ""
    for model in models:
        try:
            resp = requests.post(_api_url(), json={**payload, "model": model}, timeout=120)
            resp.raise_for_status()
            choices = resp.json().get("choices", [])
            text = (choices[0].get("message", {}).get("content") or "").strip() if choices else ""
            match = re.search(r"[.!?\n]", text)
            if match:
                text = text[: match.start()]
            elif len(text) > 120:
                text = text[:120].rsplit(" ", 1)[0]
            text = text.strip()
            break
        except Exception:
            logger.warning("LLM call failed with model %s", model, exc_info=model == models[-1])
    elapsed = time.monotonic() - t0
    if elapsed < min_delay:
        time.sleep(min_delay - elapsed)
    return text


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def preload_model():
    """Warm the model so the first real request isn't cold."""
    try:
        _generate([], "(warmup)", max_new_tokens=5)
        logger.info("Chat model warmed up")
    except Exception:
        logger.debug("Warmup skipped (server may not be running)", exc_info=True)


def _quant():
    """Return model identifier. Used by the bench harness."""
    return Config().get("chat_model", "gemma4")


# Bench-compat alias
_generate_sync = _generate


def set_stream_context(game: str | None):
    """Update the current game being streamed. Pass None to clear."""
    global _stream_context
    _stream_context = game or None


def generate_chat_message(dialog=None, trigger=None, thread=None, channel=None) -> str:
    return _generate(dialog or [], trigger, thread, channel=channel)


def generate_event_response(trigger: str) -> str:
    return _generate([], trigger, system_prompt=EVENT_SYSTEM_PROMPT)


def chat_filter(prompt: str, msg: str) -> bool:
    """Return True if msg is worth responding to."""
    if msg == prompt:
        return False
    if len(msg) == len(prompt) + 1:
        return False
    if msg.startswith("/"):
        return False
    if msg == " ":
        return False
    return True
