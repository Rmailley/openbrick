from openbrick.imessage import format_incoming, incoming_message

CONTACTS = {"mom": "+15550001111"}


def msg(**data):
    base = {
        "isFromMe": False,
        "text": "are you coming?",
        "handle": {"address": "+15550001111"},
        "chats": [{"guid": "iMessage;-;+15550001111"}],
    }
    base.update(data)
    return base


def test_direct_message_uses_contact_name():
    assert format_incoming(msg(), CONTACTS) == ("iMessage;-;+15550001111", "[mom] are you coming?")


def test_green_bubble_text_keeps_its_sms_chat():
    m = msg(chats=[{"guid": "SMS;-;+15550001111"}])
    assert format_incoming(m, CONTACTS) == ("SMS;-;+15550001111", "[mom] are you coming?")


def test_unknown_sender_shows_address():
    m = msg(handle={"address": "+15552223333"})
    assert format_incoming(m, CONTACTS)[1] == "[+15552223333] are you coming?"


def test_group_chat_label():
    m = msg(chats=[{"guid": "iMessage;+;chat42", "displayName": "Family"}])
    assert format_incoming(m, CONTACTS) == ("iMessage;+;chat42", "[mom in Family] are you coming?")


def test_attachment_only():
    assert format_incoming(msg(text="", attachments=[{"guid": "x"}]), CONTACTS)[1] == "[mom] (sent an attachment)"
    assert format_incoming(msg(text=""), CONTACTS) is None


def test_incoming_message_filters_own_and_other_events():
    assert incoming_message({"type": "new-message", "data": msg()}) == msg()
    assert incoming_message({"type": "new-message", "data": msg(isFromMe=True)}) is None
    assert incoming_message({"type": "new-message", "data": msg(chats=[])}) is None
    assert incoming_message({"type": "typing-indicator", "data": {}}) is None
