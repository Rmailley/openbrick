import time

from openbrick.app import create_app
from test_app import FakeIMessage, FakeSMS, OWNER, make_config, webhook

MOM = "+15550001111"


class PollingIMessage(FakeIMessage):
    def __init__(self):
        super().__init__()
        self.messages = []
        self.asked = []
        self.fail = False

    def messages_after(self, since_ms):
        self.asked.append(since_ms)
        if self.fail:
            raise RuntimeError("bluebubbles is down")
        return [m for m in self.messages if m["dateCreated"] >= since_ms]


def raw(guid, text, sender=MOM, chat="iMessage;-;+15550001111", age_s=5, from_me=False):
    return {
        "guid": guid, "text": text, "isFromMe": from_me, "handle": {"address": sender},
        "chats": [{"guid": chat}], "dateCreated": int((time.time() - age_s) * 1000),
    }


def make(tmp_path):
    im, sms = PollingIMessage(), FakeSMS()
    app = create_app(make_config(tmp_path, "relay"), sms=sms, imessage=im)
    return app, im, sms


def test_poll_forwards_a_message_the_webhook_missed(tmp_path):
    app, im, sms = make(tmp_path)
    app.config["poll"]()  # first run only sets the cursor
    im.messages.append(raw("g1", "are you coming"))
    app.config["poll"]()
    assert sms.sent == ["[mom] are you coming"]


def test_webhook_and_poll_never_forward_twice(tmp_path):
    app, im, sms = make(tmp_path)
    app.config["poll"]()
    msg = raw("g2", "hello")
    client = app.test_client()
    client.post("/bluebubbles?token=hook-secret", json={"type": "new-message", "data": msg})
    im.messages.append(msg)
    app.config["poll"]()
    app.config["poll"]()
    assert len(sms.sent) == 1


def test_poll_then_late_webhook_is_still_one_forward(tmp_path):
    app, im, sms = make(tmp_path)
    app.config["poll"]()
    msg = raw("g3", "hi there")
    im.messages.append(msg)
    app.config["poll"]()
    app.test_client().post("/bluebubbles?token=hook-secret", json={"type": "new-message", "data": msg})
    assert len(sms.sent) == 1


def test_poll_ignores_my_own_messages(tmp_path):
    app, im, sms = make(tmp_path)
    app.config["poll"]()
    im.messages.append(raw("g4", "sent by me", from_me=True))
    app.config["poll"]()
    assert sms.sent == []


def test_poll_runs_owner_commands_once(tmp_path):
    app, im, sms = make(tmp_path)
    app.config["poll"]()
    im.messages.append(raw("g5", "help", sender=OWNER, chat=f"SMS;-;{OWNER}"))
    app.config["poll"]()
    app.config["poll"]()
    assert len(sms.sent) == 1 and sms.sent[0].startswith("openBrick:")


def test_a_failed_poll_is_survivable_and_retried(tmp_path):
    app, im, sms = make(tmp_path)
    app.config["poll"]()
    im.messages.append(raw("g6", "still here"))
    im.fail = True
    app.config["poll"]()  # must not raise
    assert sms.sent == []
    im.fail = False
    app.config["poll"]()
    assert len(sms.sent) == 1


def test_seen_messages_survive_a_restart(tmp_path):
    app, im, sms = make(tmp_path)
    app.config["poll"]()
    im.messages.append(raw("g7", "once only"))
    app.config["poll"]()
    app2 = create_app(make_config(tmp_path, "relay"), sms=sms, imessage=im)
    app2.config["poll"]()
    assert len(sms.sent) == 1


def test_catch_up_after_downtime_is_capped(tmp_path):
    app, im, sms = make(tmp_path)
    im.messages.append(raw("old", "ancient", age_s=5 * 3600))
    app.config["poll"]()
    assert sms.sent == []
    assert im.asked[0] >= int((time.time() - 3 * 3600) * 1000)
