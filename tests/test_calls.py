from types import SimpleNamespace

from openbrick.calls import Caller
from openbrick.contacts import ContactBook
from openbrick.router import Router
from openbrick.state import State

OWNER, MAIN = "+15551234567", "+15559990000"


class FakeTwilio:
    def __init__(self, fail=False):
        self.created = []
        self.fail = fail
        self.calls = SimpleNamespace(create=self._create)

    def _create(self, **kw):
        if self.fail:
            raise RuntimeError("twilio is down")
        self.created.append(kw)


def test_rings_the_dumbphone_from_the_main_number_then_dials_out_with_it():
    twilio = FakeTwilio()
    Caller(twilio, OWNER, MAIN).call("+12025550101", "Mom & Dad <3")
    [call] = twilio.created
    assert call["to"] == OWNER and call["from_"] == MAIN
    assert call["twiml"] == (
        "<Response><Say>Connecting you to Mom &amp; Dad &lt;3.</Say>"
        f'<Dial callerId="{MAIN}">+12025550101</Dial></Response>'
    )


BOOK = [
    {"firstName": "Henry", "lastName": "Lee", "phoneNumbers": [{"address": "(202) 555-0103"}]},
    {"firstName": "Mike", "lastName": "Chen", "phoneNumbers": [{"address": "(202) 555-0101"}]},
    {"firstName": "Mike", "lastName": "Ross", "phoneNumbers": [{"address": "(202) 555-0102"}]},
    {"firstName": "Email", "lastName": "Only", "emails": [{"address": "eo@icloud.com"}]},
]


def make(tmp_path, twilio=None):
    twilio = twilio or FakeTwilio()
    book = ContactBook({"mom": "+15550001111"}, fetch=lambda: BOOK)
    router = Router(book, State(tmp_path / "s.json"), caller=Caller(twilio, OWNER, MAIN))
    return router, twilio


def numbers(twilio):
    return [c["twiml"].split(">")[-3].split("<")[0] for c in twilio.created]


def test_exact_name_calls_right_away(tmp_path):
    router, twilio = make(tmp_path)
    assert router.handle("call henry") == "Calling you now. Answer to reach Henry Lee."
    assert router.handle("Call MOM") == "Calling you now. Answer to reach mom."
    assert numbers(twilio) == ["+12025550103", "+15550001111"]


def test_a_corrected_name_asks_before_calling(tmp_path):
    router, twilio = make(tmp_path)
    assert router.handle("call henny") == "Call Henry Lee? Reply y to call."
    assert twilio.created == []
    router.handle("y")
    assert numbers(twilio) == ["+12025550103"]


def test_ambiguous_name_asks_which(tmp_path):
    router, twilio = make(tmp_path)
    assert router.handle("call mike") == "Call which mike?\n1 Mike Chen\n2 Mike Ross\nReply a number."
    router.handle("2")
    assert numbers(twilio) == ["+12025550102"]


def test_raw_numbers_work_and_short_ones_dont(tmp_path):
    router, twilio = make(tmp_path)
    assert router.handle("call (202) 555-0199") == "Calling you now. Answer to reach +12025550199."
    assert router.handle("call 555019999999") == "Use a full number with area code, like call 2025550123."
    assert router.handle("call 5550199") == "No contact named 5550199."
    assert numbers(twilio) == ["+12025550199"]


def test_contacts_without_a_phone_number_cant_be_called(tmp_path):
    router, _ = make(tmp_path)
    assert router.handle("call email only") == "Email Only has no phone number saved."
    assert router.handle("call nobody") == "No contact named nobody."


def test_failures_and_missing_setup_are_explained(tmp_path):
    router, _ = make(tmp_path, FakeTwilio(fail=True))
    assert router.handle("call henry") == "Couldn't place the call."
    bare = Router(ContactBook({}, fetch=lambda: BOOK), State(tmp_path / "t.json"))
    assert bare.handle("call henry") == "Calls aren't set up. Add a calls section to config.yaml."
