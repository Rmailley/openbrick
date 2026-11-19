import json

import pytest

from openbrick.llm import SCHEMA, Interpreter, to_command


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def raise_for_status(self):
        pass

    def json(self):
        return self.body


class FakeSession:
    def __init__(self, content):
        self.content = content
        self.calls = []

    def post(self, url, **kw):
        self.calls.append((url, kw))
        return FakeResponse({"choices": [{"message": {"content": self.content}}]})


def test_sends_schema_constrained_openai_style_request():
    session = FakeSession(json.dumps({"action": "message", "contact": "sam"}))
    llm = Interpreter("http://127.0.0.1:8081/", "qwen", session=session)
    assert llm.interpret("txt sam running late", {"contacts": ["sam"], "places": []}) == "@sam running late"

    url, kw = session.calls[0]
    body = kw["json"]
    assert url == "http://127.0.0.1:8081/v1/chat/completions"
    assert body["model"] == "qwen" and body["temperature"] == 0
    assert body["response_format"]["json_schema"]["schema"] == SCHEMA
    assert "contacts: sam\nplaces: (none)" in body["messages"][0]["content"]
    assert body["messages"][-1] == {"role": "user", "content": "txt sam running late"}


def test_garbled_model_output_means_no_command():
    assert Interpreter("http://o", "m", session=FakeSession("not json")).interpret("x", {}) is None
    assert Interpreter("http://o", "m", session=FakeSession("[1]")).interpret("x", {}) is None
    assert Interpreter("http://o", "m", session=FakeSession('{"action": "none"}')).interpret("x", {}) is None

    class NoChoices(FakeSession):
        def post(self, url, **kw):
            return FakeResponse({"choices": []})

    assert Interpreter("http://o", "m", session=NoChoices("")).interpret("x", {}) is None


@pytest.mark.parametrize(
    "fields, original, expected",
    [
        ({"action": "reply"}, "rply be thrre in 5", "r be thrre in 5"),
        ({"action": "reply"}, "ok sounds good", None),
        ({"action": "reply"}, "rply", None),
        ({"action": "message", "contact": "dad"}, "tell dad i love u\nsee u sun", "@dad i love u\nsee u sun"),
        ({"action": "message", "contact": "mom"}, "@mmo on my way", "@mom on my way"),
        ({"action": "message", "contact": "sam"}, "msg sam", None),
        ({"action": "message", "contact": "sam"}, "please could you tell my friend sam hi", None),
        ({"action": "directions", "origin": "home", "destination": "Union Station"},
         "dir hom 2 union statoin", "go home to Union Station"),
        ({"action": "directions", "origin": "home"}, "dir hom", None),
        ({"action": "2fa", "pin": "0421", "account": "github"}, "2fa 0421 gtihub", "2fa 0421 github"),
        ({"action": "2fa", "pin": "9999", "account": "github"}, "2fa 0421 gtihub", None),
        ({"action": "help", "text": "help"}, "hlep", "help"),
        ({"action": "none"}, "instagram", None),
    ],
)
def test_to_command_only_uses_the_senders_own_words(fields, original, expected):
    assert to_command(fields, original) == expected
