from openbrick.mute import MUTE_SECONDS, Mutes
from openbrick.state import State

GROUP = "iMessage;+;chat1"


class Clock:
    now = 1000.0

    def __call__(self):
        return self.now


class FakeSummarizer:
    def __init__(self, summary="Sam wants to know about 7."):
        self.summary = summary
        self.seen = []

    def summarize(self, chat, messages):
        self.seen.append((chat, messages))
        return self.summary


def make(tmp_path, summarizer=None):
    clock = Clock()
    return Mutes(State(tmp_path / "s.json"), summarizer, clock), clock


def test_held_messages_are_summarized_on_release(tmp_path):
    summarizer = FakeSummarizer()
    mutes, _ = make(tmp_path, summarizer)
    mutes.mute(GROUP, "Family")
    assert mutes.is_muted(GROUP)
    mutes.hold(GROUP, "sam", "free at 7?")
    mutes.hold(GROUP, "mom", "me too")
    assert mutes.release(GROUP) == "Unmuted Family. 2 missed: Sam wants to know about 7."
    assert summarizer.seen == [("Family", [("sam", "free at 7?"), ("mom", "me too")])]
    assert not mutes.is_muted(GROUP)


def test_falls_back_to_a_plain_summary_without_claude(tmp_path):
    for summarizer in (None, FakeSummarizer(summary=None)):
        mutes, _ = make(tmp_path, summarizer)
        mutes.mute(GROUP, "Family")
        mutes.hold(GROUP, "sam", "free at 7?")
        assert mutes.release(GROUP) == "Unmuted Family. 1 missed: 1 from sam. Latest: sam: free at 7?"


def test_nothing_to_summarize(tmp_path):
    mutes, _ = make(tmp_path)
    mutes.mute(GROUP, "Family")
    assert mutes.release(GROUP) == "Unmuted Family. Nothing new."


def test_muting_again_extends_without_losing_held_messages(tmp_path):
    mutes, clock = make(tmp_path)
    mutes.mute(GROUP, "Family")
    mutes.hold(GROUP, "sam", "hi")
    clock.now += 1800
    mutes.mute(GROUP, "Family")
    clock.now += MUTE_SECONDS - 1
    assert mutes.sweep() == []  # still muted: the hour restarted
    assert mutes.release(GROUP).startswith("Unmuted Family. 1 missed")


def test_sweep_releases_only_expired_mutes_and_skips_silent_ones(tmp_path):
    mutes, clock = make(tmp_path)
    mutes.mute(GROUP, "Family")
    mutes.mute("iMessage;+;chat2", "Work")
    mutes.hold("iMessage;+;chat2", "bo", "standup moved")
    assert mutes.sweep() == []
    clock.now += MUTE_SECONDS
    assert mutes.sweep() == ["Mute over: Work. 1 missed: 1 from bo. Latest: bo: standup moved"]
    assert not mutes.is_muted(GROUP) and not mutes.is_muted("iMessage;+;chat2")


def test_survives_a_restart(tmp_path):
    mutes, _ = make(tmp_path)
    mutes.mute(GROUP, "Family")
    mutes.hold(GROUP, "sam", "hi")
    reloaded = Mutes(State(tmp_path / "s.json"))
    assert reloaded.is_muted(GROUP)
    assert reloaded.release(GROUP).startswith("Unmuted Family. 1 missed")


def test_release_all_covers_every_muted_group(tmp_path):
    mutes, _ = make(tmp_path)
    assert mutes.release_all() is None
    mutes.mute(GROUP, "Family")
    mutes.mute("iMessage;+;chat2", "Work")
    assert mutes.release_all() == "Unmuted Family. Nothing new.\n\nUnmuted Work. Nothing new."
