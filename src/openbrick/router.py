import logging
import re

import requests

from .contacts import Contact, ContactBook, normalize_address
from .directions import PlaceNotFound
from .imessage import describe, direct_chat_guid
from .state import State

log = logging.getLogger("openbrick.router")

HELP = (
    "openBrick: r msg = reply to last. "
    "@name msg = iMessage someone. "
    "call name = call from your main number. "
    "mute / unmute = silence the last group for 1 hr, then a summary. "
    "go A to B = transit directions. "
    "2fa PIN acct = get a code. "
    "help = this list."
)
UNKNOWN = "Unknown command. Text help for the list."
MAX_CHOICES = 5

SEND = re.compile(r"^(?:@|to\s+)(\S.*)$", re.IGNORECASE | re.DOTALL)
RAW_ADDRESS = re.compile(r"^(\+\d{7,15}|\S+@\S+\.\S+)\s+(.+)$", re.DOTALL)
REPLY = re.compile(r"^r\s+(.+)$", re.IGNORECASE | re.DOTALL)
GO = re.compile(r"^(?:go|dir|directions)\s+(?:from\s+)?(.+?)\s+to\s+(.+)$", re.IGNORECASE | re.DOTALL)
GO_NO_ORIGIN = re.compile(r"^(?:go|dir|directions)\s+to\s+(.+)$", re.IGNORECASE | re.DOTALL)
CALL = re.compile(r"^call\s+(\S.*)$", re.IGNORECASE | re.DOTALL)
RAW_NUMBER = re.compile(r"^\+?[\d\s().-]{10,}$")
TWOFA = re.compile(r"^2fa(?:\s+(\S+))?(?:\s+(\S+))?$", re.IGNORECASE)


class Unresolved(Exception):
    """The text didn't parse, or named something unknown; the message is what to tell the user."""


class Router:
    def __init__(
        self,
        book: ContactBook,
        state: State,
        imessage=None,
        twofa=None,
        directions=None,
        interpreter=None,
        caller=None,
        mutes=None,
    ):
        self.book = book
        self.state = state
        self.imessage = imessage
        self.twofa = twofa
        self.directions = directions
        self.interpreter = interpreter
        self.caller = caller
        self.mutes = mutes

    def handle(self, body: str) -> str | None:
        text = body.strip()

        if pending := self.state.get("pending"):
            self.state.set("pending", None)
            if (answer := self._answer_pending(pending, text.lower())) is not None:
                return answer

        try:
            return self._run(text)
        except Unresolved as e:
            error = str(e)

        if self.interpreter is None:
            return error
        try:
            command = self.interpreter.interpret(text, self._known_names())
        except requests.RequestException as e:
            log.warning("typo-fixing model unreachable: %s", e)
            return error
        if not command or command.lower() == text.lower():
            return error
        if m := SEND.match(command):
            # Whatever the model guessed, a message only goes out after you confirm who it's for.
            return self._explain(lambda: self._send_to(m[1], confirm=True))
        if REPLY.match(command):
            self.state.set("pending", {"kind": "command", "command": command})
            return f"Did you mean: {command}\nReply y to send."
        result = self._explain(lambda: self._run(command))
        if GO.match(command):
            # The model may have "fixed" a place name wrongly, so show what was searched.
            result = f"({command})\n{result}"
        return result

    def _answer_pending(self, pending: dict, answer: str) -> str | None:
        kind = pending.get("kind")
        if kind == "choose" and answer.isdigit() and 1 <= int(answer) <= len(pending["options"]):
            option = pending["options"][int(answer) - 1]
            return self._send_contact(_addresses(option), pending["message"], option["name"])
        if kind == "send" and answer in ("y", "yes"):
            return self._send_contact(_addresses(pending), pending["message"], pending["name"])
        if kind == "call_choose" and answer.isdigit() and 1 <= int(answer) <= len(pending["options"]):
            option = pending["options"][int(answer) - 1]
            return self._place_call(option["number"], option["name"])
        if kind == "call" and answer in ("y", "yes"):
            return self._place_call(pending["number"], pending["name"])
        if kind == "command" and answer in ("y", "yes"):
            return self._explain(lambda: self._run(pending["command"]))
        if answer in ("n", "no"):
            return "Cancelled."
        return None

    def _explain(self, action) -> str:
        try:
            return action()
        except Unresolved as e:
            return str(e)

    def _known_names(self) -> dict[str, list[str]]:
        # Short names only: the whole address book would swamp a small model, and it stays out of the prompt.
        return {
            "contacts": self.book.alias_names(),
            "places": sorted(self.directions.places) if self.directions else [],
            "2fa accounts": self.twofa.accounts() if self.twofa else [],
        }

    def _run(self, text: str) -> str:
        if text.lower() in ("help", "?"):
            return HELP
        if text.lower() == "mute":
            return self._mute()
        if text.lower() == "unmute":
            return self._unmute()
        if m := CALL.match(text):
            return self._call(m[1])
        if m := SEND.match(text):
            return self._send_to(m[1])
        if m := REPLY.match(text):
            last = self.state.get("last_chat")
            if not last:
                return "Nobody to reply to yet."
            return self._send(last, m[1])
        if m := GO.match(text):
            return self._directions(m[1], m[2])
        if m := GO_NO_ORIGIN.match(text):
            return f"Where from? Text: go home to {m[1].strip()}"
        if m := TWOFA.match(text):
            if self.twofa is None:
                return "2FA isn't set up. Add a twofa section to config.yaml."
            if not m[1]:
                return "Usage: 2fa PIN account"
            return self.twofa.handle(m[1], m[2])
        log.info("unrecognized command")
        raise Unresolved(UNKNOWN)

    def _mute(self) -> str:
        last = self.state.get("last_chat")
        if self.mutes is None:
            return "Muting isn't set up."
        if not last:
            return "No chat to mute yet."
        if ";+;" not in last:
            return "Your last chat isn't a group. Only group chats can be muted."
        name = (self.state.get("chat_names") or {}).get(last, "that group")
        self.mutes.mute(last, name)
        return f"Muted {name} for 1 hr. Text unmute for a summary."

    def _unmute(self) -> str:
        if self.mutes is None:
            return "Muting isn't set up."
        return self.mutes.release_all() or "Nothing is muted."

    def _call(self, text: str) -> str:
        if self.caller is None:
            return "Calls aren't set up. Add a calls section to config.yaml."
        if RAW_NUMBER.match(text):
            number = normalize_address(text)
            if not number.startswith("+"):
                raise Unresolved("Use a full number with area code, like call 2025550123.")
            return self._place_call(number, number)

        match = self.book.match(text)
        name = text.split()[0]
        # Calls need a phone number; a contact with only an email can't be dialed.
        callable_ = [(c, next((a for a in c.addresses if a.startswith("+")), None)) for c in match.contacts]
        callable_ = [(c, n) for c, n in callable_ if n]
        if not match.contacts:
            raise Unresolved(f"No contact named {name}.")
        if not callable_:
            raise Unresolved(f"{match.contacts[0].name} has no phone number saved.")
        if len(callable_) > MAX_CHOICES:
            return f"Too many matches for {name}. Use their full name."
        if len(callable_) > 1:
            labels = [label for label, _ in _labeled([c for c, _ in callable_])]
            options = [{"name": label, "number": n} for label, (_, n) in zip(labels, callable_)]
            self.state.set("pending", {"kind": "call_choose", "options": options})
            lines = [f"{i} {o['name']}" for i, o in enumerate(options, 1)]
            return f"Call which {name}?\n" + "\n".join(lines) + "\nReply a number."
        contact, number = callable_[0]
        if not match.exact:
            self.state.set("pending", {"kind": "call", "name": contact.name, "number": number})
            return f"Call {contact.name}? Reply y to call."
        return self._place_call(number, contact.name)

    def _place_call(self, number: str, name: str) -> str:
        try:
            self.caller.call(number, name)
        except Exception as e:  # Twilio raises its own error types; don't let any of them crash the webhook
            log.error("call failed: %s", type(e).__name__)
            return "Couldn't place the call."
        log.info("calling %s", name)
        return f"Calling you now. Answer to reach {name}."

    def _send_to(self, text: str, confirm: bool = False) -> str:
        if m := RAW_ADDRESS.match(text):
            return self._send_contact([m[1]], m[2], m[1])

        match = self.book.match(text)
        name = text.split()[0].lstrip("@")
        if not match.contacts:
            raise Unresolved(f"No contact named {name}.")
        if not match.message:
            return f"What should I send? Text: @{name} your message"

        if len(match.contacts) > MAX_CHOICES:
            return f"Too many matches for {name}. Use their full name."
        if len(match.contacts) > 1:
            options = [{"name": label, "addresses": list(c.addresses)} for label, c in _labeled(match.contacts)]
            self.state.set("pending", {"kind": "choose", "options": options, "message": match.message})
            lines = [f"{i} {o['name']}" for i, o in enumerate(options, 1)]
            return f"Which {name}?\n" + "\n".join(lines) + "\nReply a number."

        contact = match.contacts[0]
        if confirm or not match.exact:
            self.state.set(
                "pending",
                {"kind": "send", "name": contact.name, "addresses": list(contact.addresses), "message": match.message},
            )
            return f'Send to {contact.name}: "{match.message}"?\nReply y to send.'
        return self._send_contact(list(contact.addresses), match.message, contact.name)

    def _send_contact(self, addresses: list[str], message: str, to: str) -> str:
        """Send to one person, trying each of their numbers and emails until Messages accepts one.

        Only iMessage-registered addresses deliver, and a contact card often lists several, so the first
        one isn't always the right one. A timeout or connection error stops the loop: the message may
        already have gone out, and retrying could send it twice.
        """
        # Remember which address worked last, so a stale number on the card costs one failure, not one per text.
        key = "|".join(sorted(addresses))
        working = self.state.get("working_addresses", {})
        if (best := working.get(key)) in addresses:
            addresses = [best] + [a for a in addresses if a != best]
        for address in addresses:
            result = self._send(direct_chat_guid(address), message, to=to, address=address)
            if result is not _REJECTED:
                if result == f"Sent to {to}." and working.get(key) != address:
                    self.state.set("working_addresses", {**working, key: address})
                return result
        return f"Couldn't send to {to}: Messages rejected {len(addresses)} address(es)."

    def _send(self, chat_guid: str, message: str, to: str | None = None, address: str | None = None):
        if self.imessage is None:
            return "iMessage isn't set up. Add a bluebubbles section to config.yaml."
        try:
            self.imessage.send_text(chat_guid, message.strip())
        except requests.HTTPError as e:
            # BlueBubbles answered, but Messages couldn't deliver it (for example, not an iMessage address).
            log.warning("send to %s rejected via address ending %s: %s", to, (address or "?")[-4:], describe(e))
            return _REJECTED if address else "Couldn't send: Messages reported an error."
        except requests.RequestException as e:
            log.error("send failed, Mac unreachable or timed out: %s", describe(e))
            return "Couldn't reach the Mac. Message not sent."
        log.info("sent message to %s", to or "last chat")
        self.state.set("last_chat", chat_guid)
        return f"Sent to {to}." if to else "Sent."

    def _directions(self, origin: str, destination: str) -> str:
        if self.directions is None:
            return "Directions aren't set up. Add a directions section to config.yaml."
        try:
            return self.directions.route(origin, destination)
        except PlaceNotFound as e:
            raise Unresolved(f"Couldn't find {e}. Try a fuller address.")
        except requests.RequestException as e:
            log.error("directions failed: %s", describe(e))
            return "Couldn't reach the trip planner. Is OpenTripPlanner running?"


_REJECTED = object()


def _addresses(item: dict) -> list[str]:
    return item.get("addresses") or [item["address"]]


def _labeled(contacts: list[Contact]) -> list[tuple[str, Contact]]:
    """Names for a pick list, adding the number's last 4 digits when two people share a name."""
    names = [c.name for c in contacts]
    return [(f"{c.name} ({c.address[-4:]})" if names.count(c.name) > 1 else c.name, c) for c in contacts]
