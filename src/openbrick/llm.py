import difflib
import json
import re

import requests

INSTRUCTIONS = """You read text messages typed on a phone keypad and work out which openBrick \
command the sender meant. Expect typos, missing spaces, "2" for "to" and T9 mistakes.

Actions:
- reply: answer whoever messaged last.
- message: message a contact. Put who in "contact".
- directions: transit directions. Put the start in "origin" and the end in "destination".
- 2fa: a login code. Put the digits in "pin" and the account in "account".
- help: list commands.
- none: anything else.

Use a known name when the sender clearly means one. Otherwise fix the spelling of place names.
"""

SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["reply", "message", "directions", "2fa", "help", "none"]},
        "contact": {"type": "string"},
        "origin": {"type": "string"},
        "destination": {"type": "string"},
        "pin": {"type": "string"},
        "account": {"type": "string"},
    },
    "required": ["action"],
}

EXAMPLES = [
    ("repyl ok cool", {"action": "reply"}),
    ("msg jen headed out now", {"action": "message", "contact": "jen"}),
    ("dirctions frm the office 2 penn statoin",
     {"action": "directions", "origin": "the office", "destination": "Penn Station"}),
    ("2fa1234 gogle", {"action": "2fa", "pin": "1234", "account": "google"}),
    ("hepl", {"action": "help"}),
    ("is it raining", {"action": "none"}),
]


def _similar(a: str, b: str) -> bool:
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio() >= 0.6


def _rest_after(text: str, word_index: int) -> str | None:
    words = list(re.finditer(r"\S+", text))
    if word_index >= len(words) - 1:
        return None
    return text[words[word_index].end():].strip()


def to_command(fields: dict, original: str) -> str | None:
    """Build a command from the model's fields. Message text always comes from the original, never the model."""
    get = lambda key: str(fields.get(key) or "").strip()
    action = fields.get("action")
    words = original.split()

    if action == "reply" and words and (words[0].lower() == "r" or _similar(words[0], "reply")):
        if message := _rest_after(original, 0):
            return f"r {message}"
    if action == "message" and (contact := get("contact").lstrip("@")):
        size = len(contact.split())
        for i in range(min(3, len(words))):
            if _similar(" ".join(words[i:i + size]).lstrip("@"), contact):
                if message := _rest_after(original, i + size - 1):
                    return f"@{contact} {message}"
                break
    if action == "directions" and get("origin") and get("destination"):
        return f"go {get('origin')} to {get('destination')}"
    if action == "2fa" and get("pin") and get("pin") in original:
        return f"2fa {get('pin')} {get('account')}".strip()
    if action == "help":
        return "help"
    return None


class Interpreter:
    """Asks a small local model (llama.cpp's llama-server, or Ollama) what a text that didn't parse meant."""

    def __init__(self, url: str, model: str, session: requests.Session | None = None):
        self.url = url.rstrip("/")
        self.model = model
        self.session = session or requests.Session()

    def interpret(self, text: str, known: dict[str, list[str]]) -> str | None:
        names = "\n".join(f"{kind}: {', '.join(values) or '(none)'}" for kind, values in known.items())
        messages = [{"role": "system", "content": f"{INSTRUCTIONS}\nKnown names:\n{names}"}]
        for example, answer in EXAMPLES:
            messages += [{"role": "user", "content": example}, {"role": "assistant", "content": json.dumps(answer)}]
        messages.append({"role": "user", "content": text})

        r = self.session.post(
            f"{self.url}/v1/chat/completions",
            json={
                "model": self.model,
                "messages": messages,
                "temperature": 0,
                "response_format": {"type": "json_schema", "json_schema": {"name": "command", "schema": SCHEMA}},
            },
            timeout=120,
        )
        r.raise_for_status()
        try:
            fields = json.loads(r.json()["choices"][0]["message"]["content"])
        except (ValueError, KeyError, IndexError, TypeError):
            return None
        return to_command(fields, text) if isinstance(fields, dict) else None
