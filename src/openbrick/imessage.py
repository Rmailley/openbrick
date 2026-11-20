import uuid

import requests


class BlueBubbles:
    def __init__(self, url: str, password: str, session: requests.Session | None = None):
        self.url = url.rstrip("/")
        self.password = password
        self.session = session or requests.Session()

    def send_text(self, chat_guid: str, text: str) -> None:
        r = self.session.post(
            f"{self.url}/api/v1/message/text",
            params={"password": self.password},
            json={
                "chatGuid": chat_guid,
                "tempGuid": str(uuid.uuid4()),
                "message": text,
                "method": "apple-script",
            },
            timeout=30,
        )
        r.raise_for_status()

    def ping(self) -> float:
        """Seconds BlueBubbles takes to answer; raises if it doesn't."""
        r = self.session.get(f"{self.url}/api/v1/ping", params={"password": self.password}, timeout=10)
        r.raise_for_status()
        return r.elapsed.total_seconds()

    def contacts(self) -> list[dict]:
        r = self.session.get(f"{self.url}/api/v1/contact", params={"password": self.password}, timeout=30)
        r.raise_for_status()
        return r.json()["data"]


def describe(error: Exception) -> str:
    """An error as safe log text. requests puts the full URL, with the BlueBubbles password, in its messages."""
    response = getattr(error, "response", None)
    if response is not None:
        return f"{type(error).__name__} (HTTP {response.status_code})"
    return type(error).__name__


def direct_chat_guid(address: str) -> str:
    return f"iMessage;-;{address}"


def incoming_message(event: dict) -> dict | None:
    """The message in a BlueBubbles webhook if someone else sent it, else None."""
    if event.get("type") != "new-message":
        return None
    msg = event.get("data") or {}
    if msg.get("isFromMe") or not msg.get("chats"):
        return None
    return msg


def sender(msg: dict) -> str:
    return (msg.get("handle") or {}).get("address", "unknown")


def describe_incoming(msg: dict, label_for) -> tuple[str, str, str | None, str] | None:
    """Break an incoming message into (chat_guid, sender, group_name, text); None if there's nothing to forward.

    group_name is None for a one-on-one chat. Attachments with no words become "(sent an attachment)".
    """
    chat = msg["chats"][0]
    group = (chat.get("displayName") or "group") if ";+;" in chat["guid"] else None
    text = (msg.get("text") or "").strip()
    if not text:
        if not msg.get("attachments"):
            return None
        text = "(sent an attachment)"
    return chat["guid"], label_for(sender(msg)), group, text


def format_incoming(msg: dict, label_for) -> tuple[str, str] | None:
    """Turn an incoming message into (chat_guid, sms_text), or None if there's nothing to forward."""
    if (d := describe_incoming(msg, label_for)) is None:
        return None
    guid, who, group, text = d
    return guid, f"[{who} in {group}] {text}" if group else f"[{who}] {text}"
