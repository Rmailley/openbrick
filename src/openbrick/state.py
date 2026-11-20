import json
import threading
from pathlib import Path


class State:
    def __init__(self, path: Path):
        self.path = path
        self._data = json.loads(path.read_text()) if path.exists() else {}
        self._lock = threading.Lock()  # the webhook, the poller and the sweeper all write

    def get(self, key: str, default=None):
        return self._data.get(key, default)

    def set(self, key: str, value) -> None:
        with self._lock:
            self._data[key] = value
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._data))
            tmp.replace(self.path)  # a crash mid-write can't leave half a file
