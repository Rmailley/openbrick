import json
from pathlib import Path


class State:
    def __init__(self, path: Path):
        self.path = path
        self._data = json.loads(path.read_text()) if path.exists() else {}

    def get(self, key: str, default=None):
        return self._data.get(key, default)

    def set(self, key: str, value) -> None:
        self._data[key] = value
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._data))
