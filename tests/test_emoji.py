import pytest

from openbrick.emoji import spell_out
from openbrick.sms import RelaySMS
from openbrick.state import State


@pytest.mark.parametrize(
    "text, expected",
    [
        ("nice 👍", "nice <thumbs up emoji>"),
        ("👍🏽", "<thumbs up emoji>"),  # skin tone dropped
        ("❤️", "<heart emoji>"),  # variation selector dropped
        ("😂😂", "<laughing emoji><laughing emoji>"),
        ("🇺🇸 hi", "<flag US emoji> hi"),
        ("1️⃣ first", "<keycap 1 emoji> first"),
        ("☕ now", "<hot beverage emoji> now"),
    ],
)
def test_emoji_become_words(text, expected):
    assert spell_out(text) == expected


def test_joined_sequence_is_named_by_its_parts():
    assert spell_out("👨‍👩‍👧") == "<man woman girl emoji>"


def test_plain_text_is_untouched():
    text = "meet at 5:30 #2 (c) 2024 © café 日本語 -> ok!"
    assert spell_out(text) == text


def test_relay_sms_spells_out_emoji(tmp_path):
    class IM:
        sent = []

        def send_text(self, chat, text):
            self.sent.append(text)

    im = IM()
    RelaySMS(im, State(tmp_path / "s.json"), "+15551234567").send("[Mom] love it ❤️")
    assert im.sent == ["[Mom] love it <heart emoji>"]
