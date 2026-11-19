import re

import requests

from .imessage import direct_chat_guid
from .state import State

HELP = (
    "openBrick: @name msg = iMessage someone. "
    "r msg = reply to last iMessage. "
    "2fa PIN acct = get a code. "
    "help = this list."
)

SEND = re.compile(r"^(?:@|to\s+)(\S+)\s+(.+)$", re.IGNORECASE | re.DOTALL)
REPLY = re.compile(r"^r\s+(.+)$", re.IGNORECASE | re.DOTALL)
TWOFA = re.compile(r"^2fa(?:\s+(\S+))?(?:\s+(\S+))?$", re.IGNORECASE)


class Router:
    def __init__(self, contacts: dict[str, str], state: State, imessage=None, twofa=None):
        self.contacts = contacts
        self.state = state
        self.imessage = imessage
        self.twofa = twofa

    def handle(self, body: str) -> str | None:
        text = body.strip()

        if text.lower() in ("help", "?"):
            return HELP
        if m := SEND.match(text):
            return self._send_to(m[1], m[2])
        if m := REPLY.match(text):
            last = self.state.get("last_chat")
            if not last:
                return "Nobody to reply to yet."
            return self._send(last, m[1])
        if m := TWOFA.match(text):
            if self.twofa is None:
                return "2FA isn't set up. Add a twofa section to config.yaml."
            if not m[1]:
                return "Usage: 2fa PIN account"
            return self.twofa.handle(m[1], m[2])
        return "Unknown command. Text help for the list."

    def _send_to(self, name: str, message: str) -> str:
        address = self.contacts.get(name.lower())
        if address is None:
            if not (re.fullmatch(r"\+\d{7,15}", name) or "@" in name):
                return f"No contact named {name}. Add them to config.yaml or use their full number."
            address = name
        return self._send(direct_chat_guid(address), message)

    def _send(self, chat_guid: str, message: str) -> str:
        if self.imessage is None:
            return "iMessage isn't set up. Add a bluebubbles section to config.yaml."
        try:
            self.imessage.send_text(chat_guid, message.strip())
        except requests.RequestException:
            return "Couldn't reach the Mac. Message not sent."
        self.state.set("last_chat", chat_guid)
        return "Sent."
