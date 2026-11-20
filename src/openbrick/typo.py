"""Typo fixing for commands, with no model and no network: edit distance against the words openBrick knows.

A Spellchecker has the same interpret() interface as llm.Interpreter, so the router treats them alike. It
returns a corrected command string, or None when nothing is close enough. Message text is never touched:
only the command word, the contact or place being named, and the 2FA account are corrected.
"""

import re

CONNECTORS = {"to", "2", "too"}
# Verb -> what it asks for. Short verbs must be typed exactly: a one-letter slip of a three-letter word
# is usually a different word ("did" is not "dir").
VERBS = {
    "reply": "reply",
    "contact": "contact",  # read-only, so a wrong guess is harmless
    "help": "help",
    "directions": "go",
    "direction": "go",
    "route": "go",
    "dir": "go",
    "go": "go",
    "message": "msg",
    "text": "msg",
    "send": "msg",
    "tell": "msg",
    "txt": "msg",
    "msg": "msg",
    "sms": "msg",
}


def distance(a: str, b: str) -> int:
    """Edit distance counting an insertion, deletion, substitution or swap of two neighbors as one edit.

    A swap ("repyl" for "reply") is one slip on a keypad, so it costs one, not two.
    """
    a, b = a.lower(), b.lower()
    rows = [list(range(len(b) + 1))]
    for i, ca in enumerate(a, 1):
        row = [i]
        for j, cb in enumerate(b, 1):
            cost = min(rows[i - 1][j] + 1, row[j - 1] + 1, rows[i - 1][j - 1] + (ca != cb))
            if i > 1 and j > 1 and ca == b[j - 2] and a[i - 2] == cb:
                cost = min(cost, rows[i - 2][j - 2] + 1)
            row.append(cost)
        rows.append(row)
    return rows[-1][-1]


def tolerance(target: str) -> int:
    """How many slips to forgive when matching a word of this length."""
    return 0 if len(target) <= 3 else 1 if len(target) <= 6 else 2


def closest(word: str, targets, allowed=tolerance) -> str | None:
    """The one target within its tolerance of `word`, or None if none is close or two are equally close."""
    scored = sorted((distance(word, t), t) for t in targets if distance(word, t) <= allowed(t))
    if not scored or (len(scored) > 1 and scored[0][0] == scored[1][0]):
        return None
    return scored[0][1]


def _rest_after(text: str, words: list[re.Match], n: int) -> str:
    """Everything after the first n words, exactly as typed."""
    return text[words[n - 1].end():].strip() if n <= len(words) else ""


def _place_tolerance(name: str) -> int:
    return max(1, len(name) // 4)


def _fix_name(phrase: str, names) -> str:
    """Swap in a known name when the phrase is a near miss of it; otherwise leave it as typed."""
    return closest(phrase, [n for n in names if n], allowed=_place_tolerance) or phrase


class Spellchecker:
    def interpret(self, text: str, known: dict[str, list[str]]) -> str | None:
        words = list(re.finditer(r"\S+", text))
        if not words:
            return None
        first = words[0].group().lower()

        accounts = known.get("2fa accounts", [])
        if m := re.fullmatch(r"2fa(\d+)", first):  # "2fa1234 google": the space got lost
            return self._twofa(m[1], words[1:], accounts)
        if len(first) == 3 and distance(first, "2fa") == 1 and len(words) > 1 and words[1].group().isdigit():
            return self._twofa(words[1].group(), words[2:], accounts)  # "2fs 1234 google"

        verb = closest(first, VERBS)
        if verb is None:
            return None
        action = VERBS[verb]

        if action == "help":
            return "help" if len(words) == 1 else None
        rest = _rest_after(text, words, 1)
        if not rest:
            return None
        if action == "reply":
            return f"r {rest}"
        if action == "contact":
            return f"contact {rest}"
        if action == "msg":
            return f"@{rest}"
        return self._directions(rest, known.get("places", []))

    def _directions(self, rest: str, places: list[str]) -> str | None:
        parts = rest.split()
        if parts and distance(parts[0], "from") <= 1 and len(parts) > 1:
            parts = parts[1:]
        for i, word in enumerate(parts):
            if word.lower() in CONNECTORS:
                origin = " ".join(parts[:i])
                destination = " ".join(parts[i + 1:])
                if not destination:
                    return None
                destination = _fix_name(destination, places)
                return f"go {_fix_name(origin, places)} to {destination}" if origin else f"go to {destination}"
        return None

    def _twofa(self, pin: str, account_words: list[re.Match], accounts: list[str]) -> str:
        account = " ".join(w.group() for w in account_words).lower()
        return f"2fa {pin} {_fix_name(account, accounts) if account else ''}".strip()


class Fallback:
    """Tries interpreters in order and uses the first answer, so the free spellchecker goes before any model."""

    def __init__(self, *interpreters):
        self.interpreters = interpreters

    def interpret(self, text: str, known: dict[str, list[str]]) -> str | None:
        for interpreter in self.interpreters:
            if command := interpreter.interpret(text, known):
                return command
        return None
