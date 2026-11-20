import logging
import time

from .claude import extractive_summary

log = logging.getLogger("openbrick.mute")

MUTE_SECONDS = 60 * 60
MAX_BUFFERED = 200


class Mutes:
    """Group chats you've silenced for a while. Their messages are held back, then summarized when you unmute.

    State lives in the `muted` key of State so a restart doesn't lose the held messages. A mute that runs out
    is released by sweep(), which the app calls once a minute and before handling each webhook.
    """

    def __init__(self, state, summarizer=None, clock=time.time):
        self.state = state
        self.summarizer = summarizer
        self.clock = clock

    def _all(self) -> dict:
        return self.state.get("muted") or {}

    def _save(self, muted: dict) -> None:
        self.state.set("muted", muted)

    def mute(self, chat_guid: str, name: str, seconds: int = MUTE_SECONDS) -> None:
        muted = self._all()
        held = muted.get(chat_guid, {}).get("held", [])  # muting again keeps what's already held
        muted[chat_guid] = {"name": name, "until": self.clock() + seconds, "held": held}
        self._save(muted)

    def is_muted(self, chat_guid: str) -> bool:
        return chat_guid in self._all()

    def hold(self, chat_guid: str, sender: str, text: str) -> None:
        muted = self._all()
        entry = muted[chat_guid]
        entry["held"] = (entry["held"] + [[sender, text]])[-MAX_BUFFERED:]
        self._save(muted)

    def release(self, chat_guid: str) -> str:
        """End a mute now and say what was missed."""
        muted = self._all()
        entry = muted.pop(chat_guid)
        self._save(muted)
        name, held = entry["name"], [tuple(m) for m in entry["held"]]
        if not held:
            return f"Unmuted {name}. Nothing new."
        summary = self.summarizer.summarize(name, held) if self.summarizer else None
        return f"Unmuted {name}. {len(held)} missed: " + (summary or extractive_summary(held))

    def release_all(self) -> str | None:
        guids = list(self._all())
        return "\n\n".join(self.release(g) for g in guids) if guids else None

    def sweep(self) -> list[str]:
        """Release every mute that has run out. Returns the texts to send; silent ones return nothing."""
        now = self.clock()
        texts = []
        for guid, entry in list(self._all().items()):
            if entry["until"] <= now:
                texts.append(self.release(guid).replace("Unmuted", "Mute over:", 1))
        return [t for t in texts if "Nothing new" not in t]
