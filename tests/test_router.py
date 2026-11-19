import requests

from openbrick.router import HELP, Router
from openbrick.state import State


class FakeIMessage:
    def __init__(self, fail=False):
        self.sent = []
        self.fail = fail

    def send_text(self, chat_guid, text):
        if self.fail:
            raise requests.ConnectionError("mac is off")
        self.sent.append((chat_guid, text))


class FakeTwoFA:
    def handle(self, pin, account):
        return f"pin={pin} account={account}"


def make(tmp_path, **kw):
    im = kw.pop("imessage", FakeIMessage())
    router = Router({"mom": "+15550001111"}, State(tmp_path / "s.json"), imessage=im, twofa=FakeTwoFA(), **kw)
    return router, im


def test_help(tmp_path):
    router, _ = make(tmp_path)
    assert router.handle("  HELP ") == HELP


def test_send_to_contact_with_at_and_to(tmp_path):
    router, im = make(tmp_path)
    assert router.handle("@Mom on my way") == "Sent."
    assert router.handle("to mom see you\nsoon") == "Sent."
    assert im.sent == [
        ("iMessage;-;+15550001111", "on my way"),
        ("iMessage;-;+15550001111", "see you\nsoon"),
    ]


def test_send_to_raw_number_and_email(tmp_path):
    router, im = make(tmp_path)
    router.handle("@+15559998888 hi")
    router.handle("@sam@icloud.com hi")
    assert [g for g, _ in im.sent] == ["iMessage;-;+15559998888", "iMessage;-;sam@icloud.com"]


def test_unknown_contact(tmp_path):
    router, im = make(tmp_path)
    assert "No contact named dad" in router.handle("@dad hi")
    assert im.sent == []


def test_reply_goes_to_last_chat(tmp_path):
    router, im = make(tmp_path)
    assert router.handle("r hello") == "Nobody to reply to yet."
    router.state.set("last_chat", "iMessage;+;chat123")
    assert router.handle("r be there at 6") == "Sent."
    assert im.sent == [("iMessage;+;chat123", "be there at 6")]


def test_mac_unreachable(tmp_path):
    router, _ = make(tmp_path, imessage=FakeIMessage(fail=True))
    assert router.handle("@mom hi") == "Couldn't reach the Mac. Message not sent."
    assert router.state.get("last_chat") is None


def test_twofa_parsing(tmp_path):
    router, _ = make(tmp_path)
    assert router.handle("2fa") == "Usage: 2fa PIN account"
    assert router.handle("2FA 0421") == "pin=0421 account=None"
    assert router.handle("2fa 0421 GitHub") == "pin=0421 account=GitHub"


def test_unknown_command(tmp_path):
    router, _ = make(tmp_path)
    assert router.handle("instagram").startswith("Unknown command")
