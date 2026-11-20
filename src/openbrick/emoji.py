"""Emoji to words, for a phone that would show them as boxes or drop the whole text.

spell_out("nice 👍") -> "nice <thumbs up emoji>". Only emoji change; everything else passes through as typed.
"""

import re
import unicodedata

# Short names for the ones people actually send; anything else falls back to its Unicode name.
NAMES = {
    "👍": "thumbs up", "👎": "thumbs down", "❤": "heart", "😂": "laughing", "🤣": "rolling laughing",
    "😭": "crying", "🙏": "praying hands", "🔥": "fire", "😊": "smiling", "😍": "heart eyes", "🎉": "party",
    "👏": "clapping", "😅": "nervous laugh", "😢": "sad", "😘": "blowing kiss", "🥰": "loving", "😎": "cool",
    "🤔": "thinking", "😉": "wink", "🙌": "raised hands", "💯": "100", "✅": "check mark", "😀": "grinning",
    "😁": "beaming", "🙂": "slight smile", "😮": "surprised", "😡": "angry", "🤷": "shrug", "🤦": "facepalm",
    "💀": "skull", "👀": "eyes", "🤝": "handshake", "💪": "flexed bicep", "👋": "wave", "😴": "sleeping",
    "🥳": "partying", "😬": "grimace", "🙄": "eye roll", "😆": "grinning squinting", "🫡": "salute",
}

# Skin tones and variation selectors are dropped: <thumbs up emoji>, whatever the shade.
_MODIFIER = "[\U0001F3FB-\U0001F3FF]"
_BASE = "[\U0001F000-\U0001F1E5\U0001F200-\U0001F3FA\U0001F400-\U0001FAFF⌚-⏿‼⁉▪-◾☀-➿⬛⬜⭐⭕]"
_REGIONAL = "[\U0001F1E6-\U0001F1FF]{2}"
_UNIT = rf"(?:{_BASE}|{_REGIONAL})️?{_MODIFIER}?"
_KEYCAP = r"[0-9#*]️?⃣"
EMOJI = re.compile(rf"{_KEYCAP}|{_UNIT}(?:‍{_UNIT})*")
_NOISE = re.compile(rf"[️‍]|{_MODIFIER}")


def _unit_name(unit: str) -> str:
    if len(unit) == 2 and all("\U0001F1E6" <= c <= "\U0001F1FF" for c in unit):
        return "flag " + "".join(chr(ord(c) - 0x1F1E6 + 65) for c in unit)
    return NAMES.get(unit) or unicodedata.name(unit, "").lower().removesuffix(" sign")


def _name(cluster: str) -> str:
    if cluster[-1] == "⃣":
        return f"keycap {cluster[0]}"
    plain = _NOISE.sub("", cluster)
    if plain in NAMES:
        return NAMES[plain]
    # A joined sequence (a family, a person with a profession): name its parts.
    units = [u for u in re.findall(rf"{_REGIONAL}|.", plain) if u]
    return " ".join(filter(None, (_unit_name(u) for u in units))) or "emoji"


def spell_out(text: str) -> str:
    return EMOJI.sub(lambda m: f"<{_name(m.group())} emoji>", text)
