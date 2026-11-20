import json
from types import SimpleNamespace

import anthropic
import httpx2 as httpx
import pytest

from openbrick.claude import ClaudeInterpreter, ClaudeSummarizer, extractive_summary

KNOWN = {"contacts": ["mom"], "places": ["home"], "2fa accounts": ["github"]}


class FakeClient:
    def __init__(self, text="", stop_reason="end_turn", error=None):
        self.calls = []
        self.messages = self
        self._reply = SimpleNamespace(
            content=[SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=text)],
            stop_reason=stop_reason,
        )
        self._error = error

    def create(self, **kw):
        self.calls.append(kw)
        if self._error:
            raise self._error
        return self._reply


def answer(**fields):
    base = {"action": "none", "contact": "", "origin": "", "destination": "", "pin": "", "account": ""}
    return json.dumps(base | fields)


def test_interpreter_asks_for_schema_constrained_json_and_builds_a_command():
    client = FakeClient(answer(action="message", contact="sam"))
    command = ClaudeInterpreter(client).interpret("tell sam running late", KNOWN)
    assert command == "@sam running late"

    call = client.calls[0]
    assert call["model"] == "claude-opus-5-5"
    assert call["output_config"]["format"]["type"] == "json_schema"
    assert call["output_config"]["format"]["schema"]["additionalProperties"] is False
    assert call["messages"][-1] == {"role": "user", "content": "tell sam running late"}
    assert "contacts: mom" in call["system"] and "2fa accounts: github" in call["system"]


def test_message_text_comes_from_the_original_not_the_model():
    client = FakeClient(answer(action="message", contact="sam", destination="I hate you"))
    assert ClaudeInterpreter(client).interpret("txt sam see u soon", KNOWN) == "@sam see u soon"


def test_texts_with_pin_like_digits_never_leave_the_machine():
    client = FakeClient(answer(action="2fa", pin="1234", account="github"))
    assert ClaudeInterpreter(client).interpret("2fa1234 githb", KNOWN) is None
    assert client.calls == []


@pytest.mark.parametrize("stop_reason", ["refusal", "max_tokens"])
def test_unusable_stops_mean_no_command(stop_reason):
    client = FakeClient(answer(action="help"), stop_reason=stop_reason)
    assert ClaudeInterpreter(client).interpret("hepl", KNOWN) is None


def test_garbled_output_means_no_command():
    assert ClaudeInterpreter(FakeClient("not json")).interpret("hepl", KNOWN) is None
    assert ClaudeInterpreter(FakeClient("[1]")).interpret("hepl", KNOWN) is None


def test_api_errors_mean_no_command_not_a_crash():
    error = anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com"))
    assert ClaudeInterpreter(FakeClient(error=error)).interpret("hepl", KNOWN) is None


def test_summarizer_flattens_and_caps_the_summary():
    client = FakeClient("Sam asked\nif you're free at 7.  " + "x" * 600)
    summary = ClaudeSummarizer(client).summarize("Family", [("sam", "free at 7?"), ("mom", "me too")])
    assert summary.startswith("Sam asked if you're free at 7. xxx") and len(summary) == 450
    prompt = client.calls[0]["messages"][0]["content"]
    assert "Group chat: Family" in prompt and "sam: free at 7?" in prompt and "mom: me too" in prompt


def test_summarizer_gives_up_quietly():
    error = anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com"))
    assert ClaudeSummarizer(FakeClient(error=error)).summarize("Family", [("sam", "hi")]) is None
    assert ClaudeSummarizer(FakeClient("x", stop_reason="refusal")).summarize("Family", [("sam", "hi")]) is None


def test_extractive_summary_names_people_and_shows_the_latest():
    held = [("sam", "a"), ("mom", "b"), ("dad", "c"), ("jo", "d"), ("sam", "e")]
    assert extractive_summary(held) == "5 from sam, mom, dad +1. Latest: dad: c | jo: d | sam: e"


def test_a_missing_key_never_breaks_message_flow():
    # The SDK raises a plain TypeError, not an APIError, when no credentials are set.
    client = FakeClient(error=TypeError("Could not resolve authentication method"))
    assert ClaudeInterpreter(client).interpret("hepl", KNOWN) is None
    assert ClaudeSummarizer(client).summarize("Family", [("sam", "hi")]) is None
