from pathlib import Path

import pytest

from openbrick.config import load

BB = "bluebubbles: {url: 'http://mac:1234', password: pw, webhook_token: t}\n"
TW = "twilio: {account_sid: AC1, auth_token: a, number: '+15557654321'}\npublic_url: https://x.example/\n"


def write(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "config.yaml"
    p.write_text("owner_number: '+15551234567'\n" + body)
    return p


def test_relay_is_default(tmp_path):
    c = load(write(tmp_path, BB))
    assert c.transport == "relay" and c.twilio is None and c.public_url is None


def test_twilio_strips_trailing_slash(tmp_path):
    c = load(write(tmp_path, "transport: twilio\n" + TW))
    assert c.public_url == "https://x.example"


@pytest.mark.parametrize(
    "body, error",
    [
        ("", "needs a bluebubbles section"),
        ("transport: twilio\n" + BB, "needs a twilio section"),
        ("transport: carrier-pigeon\n" + BB, "transport must be one of"),
        (BB + "twofa: {pin: 0421, accounts: {}}\n", "must be a quoted string"),
    ],
)
def test_bad_configs_explain_themselves(tmp_path, body, error):
    with pytest.raises(ValueError, match=error):
        load(write(tmp_path, body))


def test_optional_sections_default_off(tmp_path):
    c = load(write(tmp_path, BB))
    assert c.directions is None and c.llm is None


def test_directions_defaults_and_lowercased_places(tmp_path):
    c = load(write(tmp_path, BB + "directions: {places: {Home: '38.9,-77.0'}}\nllm: {}\n"))
    assert c.directions.otp_url == "http://127.0.0.1:8080"
    assert c.directions.places == {"home": "38.9,-77.0"}
    assert c.llm.url == "http://127.0.0.1:8081"


def test_example_config_loads():
    c = load(Path(__file__).parent.parent / "config.example.yaml")
    assert c.transport == "relay"
    assert c.twofa.pin == "0421"
    assert "home" in c.directions.places
    assert c.llm.model


def test_anthropic_and_calls_sections_are_optional(tmp_path):
    c = load(write(tmp_path, BB))
    assert c.anthropic is None and c.calls is None

    c = load(write(tmp_path, BB + "anthropic: {model: claude-haiku-5-5, summaries: false}\n"
                   "calls: {account_sid: AC1, auth_token: a, caller_id: '+15559990000'}\n"))
    assert c.anthropic.model == "claude-haiku-5-5" and c.anthropic.summaries is False
    assert c.anthropic.api_key is None
    assert c.calls.caller_id == "+15559990000"
    assert load(write(tmp_path, BB + "anthropic: {}\n")).anthropic.model == "claude-opus-5-5"


def test_load_env_reads_keys_without_overriding_the_environment(tmp_path, monkeypatch):
    from openbrick.config import load_env

    monkeypatch.delenv("OB_NEW", raising=False)
    monkeypatch.delenv("OB_EMPTY", raising=False)
    monkeypatch.setenv("OB_SET", "from-shell")
    env = tmp_path / ".env"
    env.write_text("# comment\nOB_NEW=\"abc\"\nexport OB_SET=from-file\nOB_EMPTY=\n\nnot a line\n")
    load_env(env)
    load_env(tmp_path / "missing.env")
    import os

    assert os.environ["OB_NEW"] == "abc"
    assert os.environ["OB_SET"] == "from-shell"
    assert "OB_EMPTY" not in os.environ
    monkeypatch.delenv("OB_NEW")
