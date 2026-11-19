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

    def contacts(self) -> list[dict]:
        r = self.session.get(f"{self.url}/api/v1/contact", params={"password": self.password}, timeout=30)
        r.raise_for_status()
        return r.json()["data"]


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


def format_incoming(msg: dict, label_for) -> tuple[str, str] | None:
    """Turn an incoming message into (chat_guid, sms_text), or None if there's nothing to forward."""
    chat = msg["chats"][0]
    label = label_for(sender(msg))
    if ";+;" in chat["guid"]:
        label = f"{label} in {chat.get('displayName') or 'group'}"

    text = (msg.get("text") or "").strip()
    if not text:
        if not msg.get("attachments"):
            return None
        text = "(sent an attachment)"
    return chat["guid"], f"[{label}] {text}"
