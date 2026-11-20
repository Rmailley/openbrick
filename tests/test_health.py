import logging

from openbrick.health import Stats, report


class IM:
    def __init__(self, fail=False):
        self.fail = fail

    def ping(self):
        if self.fail:
            raise RuntimeError("no route")
        return 0.05


def test_healthy_report_counts_and_resets():
    stats = Stats()
    stats.webhook()
    stats.count("forwarded")
    stats.count("forwarded")
    stats.count("commands")
    healthy, line = report(stats, IM())
    assert healthy
    assert "health ok:" in line and "bluebubbles=up 50ms" in line
    assert "forwarded=2" in line and "commands=1" in line and "last_webhook=0m" in line
    _, again = report(stats, IM())
    assert "forwarded=0" in again


def test_bluebubbles_down_is_a_problem_without_leaking_details():
    healthy, line = report(Stats(), IM(fail=True))
    assert not healthy
    assert "health PROBLEM" in line and "DOWN (RuntimeError)" in line


def test_send_failures_are_a_problem():
    stats = Stats()
    stats.count("send_failed")
    healthy, line = report(stats, IM())
    assert not healthy and "send_failures=1" in line


def test_never_heard_from_bluebubbles():
    _, line = report(Stats(), IM())
    assert "last_webhook=never" in line


def test_app_logs_a_health_line(tmp_path, caplog):
    from test_app import FakeIMessage, make_config
    from openbrick.app import create_app

    im = FakeIMessage()
    im.ping = lambda: 0.01
    app = create_app(make_config(tmp_path, "relay"), imessage=im)
    with caplog.at_level(logging.INFO, logger="openbrick.app"):
        app.config["health"]()
    assert any("health ok" in r.message for r in caplog.records)
