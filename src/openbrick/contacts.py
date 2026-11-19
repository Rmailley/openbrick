import difflib
import re
import time
from dataclasses import dataclass

import requests

REFRESH_SECONDS = 6 * 60 * 60
RETRY_SECONDS = 5 * 60


def normalize_address(address: str) -> str:
    """Put phone numbers in +15551234567 form (assuming US for 10-digit numbers) so they match iMessage senders."""
    a = address.strip()
    if "@" in a:
        return a.lower()
    digits = re.sub(r"\D", "", a)
    if a.startswith("+"):
        return "+" + digits
    if len(digits) == 10:
        return "+1" + digits
    if len(digits) == 11 and digits.startswith("1"):
        return "+" + digits
    return digits


@dataclass(frozen=True)
class Contact:
    name: str
    addresses: tuple[str, ...]
    first: str = ""
    last: str = ""
    nickname: str = ""
    alias: bool = False

    @property
    def address(self) -> str:
        return self.addresses[0]

    def keys(self) -> set[str]:
        return {k.lower() for k in (self.name, self.first, self.last, self.nickname) if k}


def parse_contacts(raw: list[dict]) -> list[Contact]:
    contacts, seen = [], set()
    for c in raw:
        first, last, nickname = (str(c.get(k) or "").strip() for k in ("firstName", "lastName", "nickname"))
        name = str(c.get("displayName") or "").strip() or f"{first} {last}".strip() or nickname
        addresses = []
        for item in (c.get("phoneNumbers") or []) + (c.get("emails") or []):
            addr = normalize_address(str(item.get("address", "") if isinstance(item, dict) else item))
            if addr and addr not in addresses:
                addresses.append(addr)
        key = (name.lower(), tuple(addresses))
        if name and addresses and key not in seen:
            seen.add(key)
            contacts.append(Contact(name, tuple(addresses), first, last, nickname))
    return contacts


@dataclass
class Match:
    contacts: list[Contact]
    message: str
    exact: bool


class ContactBook:
    """Your Mac's Contacts (via BlueBubbles), plus short names from config.yaml such as "mom"."""

    def __init__(self, aliases: dict[str, str], fetch=None, clock=time.time):
        self._aliases = [Contact(n, (normalize_address(a),), first=n, alias=True) for n, a in aliases.items()]
        self._fetch = fetch
        self._clock = clock
        self._synced: list[Contact] = []
        self._synced_at: float | None = None
        self._attempted_at: float | None = None

    def contacts(self) -> list[Contact]:
        self._sync()
        return self._aliases + self._synced

    def alias_names(self) -> list[str]:
        return sorted(c.name for c in self._aliases)

    def _sync(self, force: bool = False) -> None:
        now = self._clock()
        if self._fetch is None:
            return
        if not force and self._synced_at is not None and now - self._synced_at < REFRESH_SECONDS:
            return
        if self._attempted_at is not None and now - self._attempted_at < RETRY_SECONDS:
            return
        self._attempted_at = now
        try:
            self._synced = parse_contacts(self._fetch())
            self._synced_at = now
        except (requests.RequestException, ValueError, KeyError, TypeError):
            pass

    def match(self, text: str) -> Match:
        """Find who `text` starts with ("mike chen see you at 8") and split off the message."""
        result = self._match(self.contacts(), text)
        if not result.contacts:
            # Maybe they were just added on the iPhone.
            self._sync(force=True)
            result = self._match(self.contacts(), text)
        return result

    def _match(self, contacts: list[Contact], text: str) -> Match:
        words = list(re.finditer(r"\S+", text))

        def rest(n: int) -> str:
            return text[words[n - 1].end():].strip() if n <= len(words) else ""

        def phrase(n: int) -> str:
            return " ".join(w[0] for w in words[:n]).lower().lstrip("@")

        def exact(n: int) -> Match | None:
            hits = [c for c in contacts if phrase(n) in c.keys()]
            return Match(_prefer_aliases(hits), rest(n), exact=True) if hits else None

        # Fuzzy matches always get confirmed, so one-word names can be loose. Two-word matches stay strict
        # so a typo'd first name doesn't swallow the first word of the message.
        def fuzzy(n: int, cutoff: float) -> Match | None:
            scored = []
            for c in contacts:
                keys = [k for k in c.keys() if (" " in k) == (n > 1)]
                if keys:
                    score = max(difflib.SequenceMatcher(None, phrase(n), k).ratio() for k in keys)
                    if score >= cutoff:
                        scored.append((score, c))
            if not scored:
                return None
            best = max(s for s, _ in scored)
            return Match(_prefer_aliases([c for s, c in scored if s >= best - 0.05]), rest(n), exact=False)

        for n in (3, 2):
            if n <= len(words) and (found := exact(n)):
                return found
        one = exact(1) if words else None
        if one and len(one.contacts) == 1:
            # "henry see you" is Henry plus a message, even though "henry see" looks like Henry Lee.
            return one
        # A close full name settles which Mike ("mike chne hi" is Mike Chen) or fixes a typo'd first name.
        two = fuzzy(2, 0.8) if len(words) >= 2 else None
        if two and (one is None or set(two.contacts) <= set(one.contacts)):
            return two
        return one or (fuzzy(1, 0.6) if words else None) or Match([], "", exact=False)

    def label(self, address: str) -> str:
        """A short name for a sender: "mom", "Henry", or "Mike Chen" when there are two Mikes."""
        address = normalize_address(address)
        contacts = self.contacts()
        for c in contacts:
            if address in c.addresses:
                if c.alias or not c.first:
                    return c.name
                same_first = {o.name for o in contacts if not o.alias and o.first.lower() == c.first.lower()}
                return c.first if len(same_first) == 1 else c.name
        return address


def _prefer_aliases(hits: list[Contact]) -> list[Contact]:
    aliases = [c for c in hits if c.alias]
    if aliases:
        return aliases
    unique: dict[str, Contact] = {}
    for c in hits:
        unique.setdefault(c.address, c)
    return list(unique.values())
