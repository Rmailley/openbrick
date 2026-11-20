import requests

from openbrick.contacts import ContactBook
from openbrick.directions import PlaceNotFound
from openbrick.router import HELP, Router
from openbrick.state import State

MOM = "+15550001111"
ADDRESS_BOOK = [
    {"firstName": "Mike", "lastName": "Chen", "phoneNumbers": [{"address": "(202) 555-0101"}]},
    {"firstName": "Mike", "lastName": "Ross", "phoneNumbers": [{"address": "(202) 555-0102"}]},
    {"firstName": "Henry", "lastName": "Lee", "phoneNumbers": [{"address": "(202) 555-0103"}]},
]


class FakeIMessage:
    def __init__(self, fail=False, reject=()):
        self.sent = []
        self.fail = fail
        self.reject = reject

    def send_text(self, chat_guid, text):
        if self.fail:
            raise requests.ConnectionError("mac is off")
        if chat_guid in self.reject:
            raise requests.HTTPError("500 Message Send Error")
        self.sent.append((chat_guid, text))


class FakeTwoFA:
    def handle(self, pin, account):
        return f"pin={pin} account={account}"

    def accounts(self):
        return []


def make(tmp_path, **kw):
    im = kw.pop("imessage", FakeIMessage())
    book = ContactBook({"mom": MOM}, fetch=lambda: ADDRESS_BOOK)
    router = Router(book, State(tmp_path / "s.json"), imessage=im, twofa=FakeTwoFA(), **kw)
    return router, im


def test_help(tmp_path):
    router, _ = make(tmp_path)
    assert router.handle("  HELP ") == HELP


def test_exact_name_sends_right_away(tmp_path):
    router, im = make(tmp_path)
    assert router.handle("@Mom on my way") == "Sent to mom."
    assert router.handle("to henry see you\nsoon") == "Sent to Henry Lee."
    assert router.handle("@mike ross hi") == "Sent to Mike Ross."
    assert im.sent == [
        (f"iMessage;-;{MOM}", "on my way"),
        ("iMessage;-;+12025550103", "see you\nsoon"),
        ("iMessage;-;+12025550102", "hi"),
    ]


def test_raw_number_and_email(tmp_path):
    router, im = make(tmp_path)
    assert router.handle("@+15559998888 hi") == "Sent to +15559998888."
    router.handle("@sam@icloud.com hi")
    assert [g for g, _ in im.sent] == ["iMessage;-;+15559998888", "iMessage;-;sam@icloud.com"]


def test_two_mikes_asks_which(tmp_path):
    router, im = make(tmp_path)
    assert router.handle("@mike see you at 8") == "Which mike?\n1 Mike Chen\n2 Mike Ross\nReply a number."
    assert im.sent == []
    assert router.handle("2") == "Sent to Mike Ross."
    assert im.sent == [("iMessage;-;+12025550102", "see you at 8")]


def test_choice_out_of_range_or_other_text_drops_it(tmp_path):
    router, im = make(tmp_path)
    router.handle("@mike hi")
    assert router.handle("7").startswith("Unknown command")
    router.handle("@mike hi")
    assert router.handle("help") == HELP
    assert router.handle("1").startswith("Unknown command")
    assert im.sent == []


def test_typo_name_confirms_before_sending(tmp_path):
    router, im = make(tmp_path)
    assert router.handle("@henny running late") == 'Send to Henry Lee: "running late"?\nReply y to send.'
    assert im.sent == []
    assert router.handle("Y") == "Sent to Henry Lee."
    assert im.sent == [("iMessage;-;+12025550103", "running late")]


def test_confirmation_can_be_declined(tmp_path):
    router, im = make(tmp_path)
    router.handle("@henny hi")
    assert router.handle("n") == "Cancelled."
    assert im.sent == []


def test_unknown_contact_and_missing_message(tmp_path):
    router, im = make(tmp_path)
    assert router.handle("@zelda hi") == "No contact named zelda."
    assert router.handle("@henry") == "What should I send? Text: @henry your message"
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


class FakeDirections:
    places = {"home": "1600 Pennsylvania Ave NW"}

    def __init__(self, missing=()):
        self.missing = missing
        self.calls = []

    def route(self, origin, destination):
        for place in (origin, destination):
            if place in self.missing:
                raise PlaceNotFound(place)
        self.calls.append((origin, destination))
        return f"route {origin} -> {destination}"


def test_directions_commands(tmp_path):
    d = FakeDirections()
    router, _ = make(tmp_path, directions=d)
    assert router.handle("go home to Union Station") == "route home -> Union Station"
    assert router.handle("directions from home to dupont circle") == "route home -> dupont circle"
    assert router.handle("go to the zoo") == "Where from? Text: go home to the zoo"
    assert d.calls == [("home", "Union Station"), ("home", "dupont circle")]


def test_directions_place_not_found(tmp_path):
    router, _ = make(tmp_path, directions=FakeDirections(missing={"xyzzy"}))
    assert router.handle("go home to xyzzy") == "Couldn't find xyzzy. Try a fuller address."


class FakeInterpreter:
    def __init__(self, answer=None, fail=False):
        self.answer = answer
        self.fail = fail
        self.seen = []

    def interpret(self, text, known):
        self.seen.append((text, known))
        if self.fail:
            raise requests.ConnectionError("model is off")
        return self.answer


def test_llm_fixes_garbled_directions_and_shows_what_it_searched(tmp_path):
    llm = FakeInterpreter("go home to Dupont Circle")
    router, _ = make(tmp_path, directions=FakeDirections(missing={"dupont cirle"}), interpreter=llm)
    assert router.handle("dir hom 2 dupont cirle") == "(go home to Dupont Circle)\nroute home -> Dupont Circle"
    # Only short names go to the model, never the whole address book.
    assert llm.seen[0][1] == {"contacts": ["mom"], "places": ["home"], "2fa accounts": []}


def test_llm_message_to_a_known_name_still_asks_first(tmp_path):
    router, im = make(tmp_path, interpreter=FakeInterpreter("@henry running late"))
    assert router.handle("tell henry running late") == 'Send to Henry Lee: "running late"?\nReply y to send.'
    assert im.sent == []
    router.handle("y")
    assert im.sent == [("iMessage;-;+12025550103", "running late")]


def test_llm_message_to_ambiguous_name_asks_which(tmp_path):
    router, im = make(tmp_path, interpreter=FakeInterpreter("@mike running late"))
    assert router.handle("txt mike running late").startswith("Which mike?")
    router.handle("1")
    assert im.sent == [("iMessage;-;+12025550101", "running late")]


def test_llm_rewritten_reply_needs_confirmation(tmp_path):
    router, im = make(tmp_path, interpreter=FakeInterpreter("r see u soon"))
    router.state.set("last_chat", "SMS;-;+15550001111")
    assert router.handle("rply see u soon") == "Did you mean: r see u soon\nReply y to send."
    assert im.sent == []
    router.handle("yes")
    assert im.sent == [("SMS;-;+15550001111", "see u soon")]


def test_llm_not_consulted_for_valid_commands(tmp_path):
    llm = FakeInterpreter("@mom something else")
    router, _ = make(tmp_path, interpreter=llm)
    router.handle("@mom hi")
    router.handle("help")
    assert llm.seen == []


def test_llm_down_or_unsure_falls_back_to_plain_error(tmp_path):
    router, _ = make(tmp_path, interpreter=FakeInterpreter(fail=True))
    assert router.handle("instagrm").startswith("Unknown command")
    router, _ = make(tmp_path, interpreter=FakeInterpreter(None))
    assert router.handle("whats the weather").startswith("Unknown command")


DAD_BOOK = [
    {
        "firstName": "Dad",
        "phoneNumbers": [{"address": "(202) 555-0201"}, {"address": "(202) 555-0202"}],
        "emails": [{"address": "dad@aol.com"}],
    }
]


def test_tries_next_address_when_messages_rejects_one(tmp_path):
    im = FakeIMessage(reject={"iMessage;-;+12025550201"})
    book = ContactBook({}, fetch=lambda: DAD_BOOK)
    router = Router(book, State(tmp_path / "s.json"), imessage=im)
    assert router.handle("to dad amazing") == "Sent to Dad."
    assert im.sent == [("iMessage;-;+12025550202", "amazing")]


def test_reports_when_every_address_is_rejected(tmp_path):
    im = FakeIMessage(reject={"iMessage;-;+12025550201", "iMessage;-;+12025550202", "iMessage;-;dad@aol.com"})
    book = ContactBook({}, fetch=lambda: DAD_BOOK)
    router = Router(book, State(tmp_path / "s.json"), imessage=im)
    assert router.handle("to dad amazing") == "Couldn't send to Dad: Messages rejected 3 address(es)."


def test_unreachable_mac_does_not_retry_other_addresses(tmp_path):
    im = FakeIMessage(fail=True)
    book = ContactBook({}, fetch=lambda: DAD_BOOK)
    router = Router(book, State(tmp_path / "s.json"), imessage=im)
    assert router.handle("to dad amazing") == "Couldn't reach the Mac. Message not sent."


def test_remembers_the_address_that_worked(tmp_path):
    im = FakeIMessage(reject={"iMessage;-;+12025550201"})
    book = ContactBook({}, fetch=lambda: DAD_BOOK)
    state = State(tmp_path / "s.json")
    router = Router(book, state, imessage=im)
    router.handle("to dad one")
    attempts = []
    original = im.send_text

    def spy(chat_guid, text):
        attempts.append(chat_guid)
        return original(chat_guid, text)

    im.send_text = spy
    # A new Router reads the saved choice back from disk, as after a restart.
    router = Router(book, State(tmp_path / "s.json"), imessage=im)
    assert router.handle("to dad two") == "Sent to Dad."
    assert attempts == ["iMessage;-;+12025550202"]


def test_spellchecker_fixes_typos_through_the_router_without_a_model(tmp_path):
    from openbrick.typo import Spellchecker

    d = FakeDirections()
    router, im = make(tmp_path, directions=d, interpreter=Spellchecker())
    router.state.set("last_chat", "SMS;-;+15550001111")
    assert router.handle("hepl") == HELP
    assert router.handle("rply see u soon") == "Did you mean: r see u soon\nReply y to send."
    assert im.sent == []
    router.handle("y")
    assert im.sent == [("SMS;-;+15550001111", "see u soon")]
    assert router.handle("txt henry running late") == 'Send to Henry Lee: "running late"?\nReply y to send.'
    assert router.handle("what is for dinner") == "Unknown command. Text help for the list."


class FakeMutes:
    def __init__(self):
        self.muted = {}

    def mute(self, guid, name):
        self.muted[guid] = name

    def release_all(self):
        if not self.muted:
            return None
        names, self.muted = list(self.muted.values()), {}
        return "Unmuted " + ", ".join(names) + "."


def test_mute_silences_the_last_group_chat_and_unmute_releases_it(tmp_path):
    mutes = FakeMutes()
    router, _ = make(tmp_path, mutes=mutes)
    assert router.handle("mute") == "No chat to mute yet."
    router.state.set("last_chat", "iMessage;+;chat1")
    router.state.set("chat_names", {"iMessage;+;chat1": "Family"})
    assert router.handle("Mute") == "Muted Family for 1 hr. Text unmute for a summary."
    assert mutes.muted == {"iMessage;+;chat1": "Family"}
    assert router.handle("unmute") == "Unmuted Family."
    assert router.handle("unmute") == "Nothing is muted."


def test_only_group_chats_can_be_muted(tmp_path):
    router, _ = make(tmp_path, mutes=FakeMutes())
    router.state.set("last_chat", "iMessage;-;+15550001111")
    assert router.handle("mute") == "Your last chat isn't a group. Only group chats can be muted."


def test_spellchecker_never_turns_a_typo_into_a_mute(tmp_path):
    from openbrick.typo import Spellchecker

    mutes = FakeMutes()
    router, _ = make(tmp_path, mutes=mutes, interpreter=Spellchecker())
    router.state.set("last_chat", "iMessage;+;chat1")
    assert router.handle("cute").startswith("Unknown command")
    assert mutes.muted == {}


def test_contact_lookup_shows_numbers_without_sending_anything(tmp_path):
    book = [
        {
            "firstName": "Dad",
            "phoneNumbers": [{"address": "(202) 555-0201"}, {"address": "+44 20 7946 0958"}, {"address": "202 555 0203"}],
            "emails": [{"address": "dad@aol.com"}],
        },
        {"firstName": "Email", "lastName": "Only", "emails": [{"address": "eo@icloud.com"}]},
    ] + ADDRESS_BOOK
    im = FakeIMessage()
    router = Router(ContactBook({"mom": MOM}, fetch=lambda: book), State(tmp_path / "s.json"), imessage=im)
    assert router.handle("contact henry") == "Henry Lee: 202-555-0103"
    assert router.handle("contact dad") == "Dad: 202-555-0201, +442079460958, 202-555-0203 +1 more"
    assert router.handle("Contact mom") == "mom: 555-000-1111"
    assert router.handle("contact email only") == "Email Only: eo@icloud.com"
    assert router.handle("contact mike") == "Mike Chen: 202-555-0101\nMike Ross: 202-555-0102"
    assert router.handle("contact henny") == "Closest match:\nHenry Lee: 202-555-0103"
    assert router.handle("contact nobody") == "No contact named nobody."
    assert im.sent == []
