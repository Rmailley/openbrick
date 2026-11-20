"""An hourly one-line health report for the log. It reads nothing private: counts, timings and battery."""

import re
import subprocess
import threading
import time

from .imessage import describe


class Stats:
    """Counters since the last report, plus when the last webhook arrived."""

    def __init__(self):
        self.started = time.time()
        self.last_webhook: float | None = None
        self._counts: dict[str, int] = {}
        self._lock = threading.Lock()

    def count(self, name: str) -> None:
        with self._lock:
            self._counts[name] = self._counts.get(name, 0) + 1

    def webhook(self) -> None:
        self.last_webhook = time.time()

    def take(self) -> dict[str, int]:
        with self._lock:
            counts, self._counts = self._counts, {}
        return counts


def _ago(then: float | None) -> str:
    if then is None:
        return "never"
    minutes = int((time.time() - then) // 60)
    return f"{minutes // 60}h{minutes % 60:02d}m ago" if minutes >= 60 else f"{minutes}m ago"


def battery() -> str:
    """'96% discharging' on a Mac, or '' anywhere pmset isn't available."""
    try:
        out = subprocess.run(["pmset", "-g", "batt"], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return ""
    m = re.search(r"(\d+)%; ([a-z ]+);", out)
    return f"{m[1]}% {m[2]}" if m else ""


def report(stats: Stats, imessage) -> tuple[bool, str]:
    """(healthy, line). Unhealthy means BlueBubbles didn't answer, or sends have failed since the last report."""
    counts = stats.take()
    healthy = True
    bluebubbles = "n/a"
    if imessage is not None:
        try:
            bluebubbles = f"up {imessage.ping() * 1000:.0f}ms"
        except Exception as e:
            bluebubbles, healthy = f"DOWN ({describe(e)})", False
    failures = counts.get("send_failed", 0)
    if failures:
        healthy = False
    parts = [
        f"bluebubbles={bluebubbles}",
        f"up={_ago(stats.started).removesuffix(' ago')}",
        f"last_webhook={_ago(stats.last_webhook)}",
        f"forwarded={counts.get('forwarded', 0)}",
        f"commands={counts.get('commands', 0)}",
        f"polled={counts.get('polled', 0)}",
        f"send_failures={failures}",
    ]
    if power := battery():
        parts.append(f"battery={power}")
    return healthy, "health " + ("ok" if healthy else "PROBLEM") + ": " + " ".join(parts)
