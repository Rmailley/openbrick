import pytest

from openbrick.typo import Fallback, Spellchecker, closest, distance

KNOWN = {"contacts": ["mom"], "places": ["home", "work"], "2fa accounts": ["github", "google"]}


@pytest.mark.parametrize(
    "a, b, expected",
    [("kitten", "sitting", 3), ("", "abc", 3), ("same", "same", 0), ("reply", "repyl", 1), ("Reply", "rply", 1)],
)
def test_distance(a, b, expected):
    assert distance(a, b) == expected


def test_closest_refuses_ties_and_short_word_slips():
    assert closest("hepl", ["help", "reply"]) == "help"
    assert closest("did", ["dir"]) is None  # three-letter words must be exact
    assert closest("mark", ["bark", "park"]) is None  # equally close to two: don't guess


@pytest.mark.parametrize(
    "text, expected",
    [
        ("rply be there in 5", "r be there in 5"),
        ("repyl ok\ncool", "r ok\ncool"),
        ("txt sam running late", "@sam running late"),
        ("mesage sam hi", "@sam hi"),
        ("hepl", "help"),
        ("dirctions hom 2 union statoin", "go home to union statoin"),
        ("directions frm work to the zoo", "go work to the zoo"),
        ("go to home", "go to home"),
        ("dirrections 2 wrok", "go to work"),
        ("2fa1234 gogle", "2fa 1234 google"),
        ("2fa1234", "2fa 1234"),
        ("2fs 1234 githb", "2fa 1234 github"),
    ],
)
def test_fixes_typos(text, expected):
    assert Spellchecker().interpret(text, KNOWN) == expected


@pytest.mark.parametrize(
    "text",
    [
        "is it raining",
        "did you go to the store",  # "did" is not "dir"
        "helpful tips",  # only a lone help word is help
        "reply",  # nothing to send
        "go",
        "dir hom",  # no "to": can't tell origin from destination
        "2fa",
        "",
    ],
)
def test_leaves_other_texts_alone(text):
    assert Spellchecker().interpret(text, KNOWN) is None


def test_unknown_places_pass_through_as_typed():
    assert Spellchecker().interpret("dir hom 2 dupont cirle", KNOWN) == "go home to dupont cirle"


def test_fallback_uses_first_answer_and_skips_the_model_when_it_can():
    class Model:
        calls = 0

        def interpret(self, text, known):
            Model.calls += 1
            return "help"

    chain = Fallback(Spellchecker(), Model())
    assert chain.interpret("hepl", KNOWN) == "help" and Model.calls == 0
    assert chain.interpret("is it raining", KNOWN) == "help" and Model.calls == 1
