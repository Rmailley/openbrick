from pathlib import Path

import pytest
from twilio.request_validator import RequestValidator

from openbrick.app import create_app
from openbrick.config import BlueBubblesConfig, Config, TwilioConfig

PUBLIC = "https://brick.example.net"
OWNER = "+15551234567"
MOM = "+15550001111"


class FakeSMS:
    def __init__(self):
        self.sent = []

    def send(self, text):
        self.sent.append(text)


class FakeIMessage:
    def __init__(self):
        self.sent = []

    def send_text(self, chat_guid, text):
        self.sent.append((chat_guid, text))

    def contacts(self):
        return []


def make_config(tmp_path: Path, transport: str) -> Config:
    return Config(
        transport=transport,
        owner_number=OWNER,
        bluebubbles=BlueBubblesConfig("http://mac.local:1234", "pw", "hook-secret"),
        twilio=TwilioConfig("AC123", "authtoken", "+15557654321") if transport == "twilio" else None,
        public_url=PUBLIC if transport == "twilio" else None,
        twofa=None,
        contacts={"mom": MOM},
        data_dir=tmp_path,
    )


def webhook(client, sender, text, chat, from_me=False, token="hook-secret"):
    payload = {
        "type": "new-message",
        "data": {"isFromMe": from_me, "text": text, "handle": {"address": sender}, "chats": [{"guid": chat}]},
    }
    return client.post(f"/bluebubbles?token={token}", json=payload)


# Relay: the dumbphone and the Mac talk through your iPhone's own number.


@pytest.fixture
def relay(tmp_path):
    im = FakeIMessage()
    return create_app(make_config(tmp_path, "relay"), imessage=im).test_client(), im


def test_relay_forwards_messages_to_the_dumbphone(relay):
    client, im = relay
    assert webhook(client, MOM, "dinner?", f"iMessage;-;{MOM}").status_code == 204
    assert im.sent == [(f"SMS;-;{OWNER}", "[mom] dinner?")]


def test_relay_command_from_dumbphone_is_answered_in_its_chat(relay):
    client, im = relay
    webhook(client, OWNER, "@mom on my way", f"any;-;{OWNER}")
    assert im.sent == [
        (f"iMessage;-;{MOM}", "on my way"),
        (f"any;-;{OWNER}", "Sent to mom."),
    ]
    webhook(client, MOM, "ok!", f"iMessage;-;{MOM}")
    assert im.sent[-1] == (f"any;-;{OWNER}", "[mom] ok!")


def test_relay_names_senders_from_the_address_book(tmp_path):
    class WithContacts(FakeIMessage):
        def contacts(self):
            return [{"firstName": "Henry", "lastName": "Lee", "phoneNumbers": [{"address": "(202) 555-0103"}]}]

    im = WithContacts()
    client = create_app(make_config(tmp_path, "relay"), imessage=im).test_client()
    webhook(client, "+12025550103", "running late?", "iMessage;-;+12025550103")
    assert im.sent == [(f"SMS;-;{OWNER}", "[Henry] running late?")]


def test_relay_reply_threads_to_last_sender(relay):
    client, im = relay
    webhook(client, MOM, "dinner?", f"SMS;-;{MOM}")
    webhook(client, OWNER, "r yes", f"SMS;-;{OWNER}")
    assert (f"SMS;-;{MOM}", "yes") in im.sent


def test_relay_ignores_its_own_outgoing_messages(relay):
    client, im = relay
    webhook(client, OWNER, "[mom] dinner?", f"SMS;-;{OWNER}", from_me=True)
    webhook(client, MOM, "sent from my iphone", f"iMessage;-;{MOM}", from_me=True)
    assert im.sent == []


def test_relay_rejects_bad_token_and_has_no_twilio_route(relay):
    client, im = relay
    assert webhook(client, OWNER, "help", f"SMS;-;{OWNER}", token="wrong").status_code == 403
    assert client.post("/sms", data={"From": OWNER, "Body": "help"}).status_code == 404
    assert im.sent == []


# Twilio: for people without an iPhone. Commands go to a Twilio number instead.


@pytest.fixture
def twilio(tmp_path):
    sms, im = FakeSMS(), FakeIMessage()
    return create_app(make_config(tmp_path, "twilio"), sms=sms, imessage=im).test_client(), sms, im


def post_sms(client, form, sign=True):
    headers = {}
    if sign:
        headers["X-Twilio-Signature"] = RequestValidator("authtoken").compute_signature(PUBLIC + "/sms", form)
    return client.post("/sms", data=form, headers=headers)


def test_twilio_owner_command_gets_reply(twilio):
    client, _, im = twilio
    r = post_sms(client, {"From": OWNER, "Body": "@mom hi"})
    assert "<Message>Sent to mom.</Message>" in r.get_data(as_text=True)
    assert im.sent == [(f"iMessage;-;{MOM}", "hi")]


def test_twilio_unsigned_or_stranger_ignored(twilio):
    client, _, im = twilio
    assert post_sms(client, {"From": OWNER, "Body": "@mom hi"}, sign=False).status_code == 403
    assert "<Message>" not in post_sms(client, {"From": "+15550009999", "Body": "@mom hi"}).get_data(as_text=True)
    assert im.sent == []


def test_twilio_forwards_imessages_and_ignores_owner_texts_to_mac(twilio):
    client, sms, im = twilio
    webhook(client, MOM, "dinner?", f"iMessage;-;{MOM}")
    webhook(client, OWNER, "help", f"SMS;-;{OWNER}")
    assert sms.sent == ["[mom] dinner?"]
    post_sms(client, {"From": OWNER, "Body": "r yes"})
    assert im.sent == [(f"iMessage;-;{MOM}", "yes")]
