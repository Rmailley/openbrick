import pytest
import requests

from openbrick.contacts import ContactBook, normalize_address, parse_contacts

RAW = [
    {"firstName": "Mike", "lastName": "Chen", "displayName": "Mike Chen",
     "phoneNumbers": [{"address": "(202) 555-0101", "id": 1}], "emails": [{"address": "Mike@Example.com"}]},
    {"firstName": "Mike", "lastName": "Ross", "displayName": "",
     "phoneNumbers": [{"address": "202.555.0102"}], "emails": []},
    {"firstName": "Henry", "lastName": "Lee", "nickname": "Hank",
     "phoneNumbers": [{"address": "+1 202 555 0103"}], "emails": []},
    {"firstName": "Sam", "lastName": "Ortiz", "phoneNumbers": [{"address": "2025550104"}], "emails": []},
    # BlueBubbles can list the same person twice (its own database and macOS Contacts).
    {"firstName": "Sam", "lastName": "Ortiz", "phoneNumbers": [{"address": "2025550104"}], "emails": []},
    {"firstName": "", "lastName": "", "phoneNumbers": [{"address": "2025550199"}]},
    {"firstName": "No", "lastName": "Number", "phoneNumbers": [], "emails": []},
]


def book(raw=RAW, aliases=None, **kw):
    return ContactBook(aliases if aliases is not None else {"mom": "+15550001111"}, fetch=lambda: raw, **kw)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("(202) 555-0101", "+12025550101"),
        ("1-202-555-0101", "+12025550101"),
        ("+44 20 7946 0958", "+442079460958"),
        (" Sam@iCloud.com ", "sam@icloud.com"),
        ("22395", "22395"),
    ],
)
def test_normalize_address(raw, expected):
    assert normalize_address(raw) == expected


def test_parse_contacts_normalizes_merges_and_skips_unusable():
    contacts = parse_contacts(RAW)
    assert [c.name for c in contacts] == ["Mike Chen", "Mike Ross", "Henry Lee", "Sam Ortiz"]
    assert contacts[0].addresses == ("+12025550101", "mike@example.com")
    assert contacts[2].nickname == "Hank"


def test_exact_first_name_with_two_people_returns_both():
    m = book().match("mike see you at 8")
    assert [c.name for c in m.contacts] == ["Mike Chen", "Mike Ross"]
    assert m.message == "see you at 8" and m.exact


def test_full_name_picks_one_and_keeps_the_message():
    m = book().match("Mike Ross see you at 8")
    assert [c.name for c in m.contacts] == ["Mike Ross"] and m.message == "see you at 8" and m.exact


def test_last_name_and_nickname_match():
    assert book().match("chen hi").contacts[0].name == "Mike Chen"
    assert book().match("hank hi").contacts[0].name == "Henry Lee"


def test_typo_matches_fuzzily():
    m = book().match("henny running late")
    assert [c.name for c in m.contacts] == ["Henry Lee"]
    assert m.message == "running late" and not m.exact
    m = book().match("mike chne hi")
    assert [c.name for c in m.contacts] == ["Mike Chen"] and m.message == "hi"


def test_unique_first_name_does_not_swallow_a_word_that_looks_like_the_last_name():
    m = book().match("henry see you soon")
    assert [c.name for c in m.contacts] == ["Henry Lee"] and m.message == "see you soon" and m.exact


def test_equally_close_typos_are_all_offered():
    raw = RAW + [{"firstName": "Jenny", "lastName": "Park", "phoneNumbers": [{"address": "2025550105"}]}]
    assert sorted(c.name for c in book(raw).match("henny hi").contacts) == ["Henry Lee", "Jenny Park"]


def test_aliases_win_and_short_typos_still_match():
    assert [c.name for c in book().match("mom hi").contacts] == ["mom"]
    m = book().match("mmo on my way")
    assert [c.name for c in m.contacts] == ["mom"] and m.message == "on my way" and not m.exact


def test_no_match():
    assert book().match("zelda hi").contacts == []


def test_label_uses_first_name_unless_shared():
    b = book()
    assert b.label("+12025550103") == "Henry"
    assert b.label("(202) 555-0101") == "Mike Chen"
    assert b.label("mike@example.com") == "Mike Chen"
    assert b.label("+15550001111") == "mom"
    assert b.label("+19995550000") == "+19995550000"


def test_sync_is_cached_and_retried_on_a_miss():
    calls, now = [], [0.0]

    def fetch():
        calls.append(now[0])
        return RAW if len(calls) == 1 else RAW + [{"firstName": "Zelda", "phoneNumbers": [{"address": "2025550106"}]}]

    b = ContactBook({}, fetch=fetch, clock=lambda: now[0])
    b.match("mike hi")
    b.match("henry hi")
    assert len(calls) == 1
    assert b.match("zelda hi").contacts == []  # just synced, too soon to ask again
    now[0] += 5 * 60
    assert b.match("zelda hi").contacts[0].name == "Zelda"
    assert len(calls) == 2


def test_sync_failure_keeps_aliases_working():
    def fetch():
        raise requests.ConnectionError("mac asleep")

    b = ContactBook({"mom": "+15550001111"}, fetch=fetch)
    assert [c.name for c in b.match("mom hi").contacts] == ["mom"]
