import logging
from xml.sax.saxutils import escape

log = logging.getLogger("openbrick.calls")


class Caller:
    """Rings the dumbphone from your main number, then connects you to the person you asked for.

    Twilio first calls `owner_number` as `caller_id`, so the dumbphone shows your main number. When you
    answer, it dials the other person with the same caller ID, so they see your main number too. Both numbers
    must be your Twilio account's verified caller IDs (the main number once; the dumbphone isn't needed).
    """

    def __init__(self, client, owner_number: str, caller_id: str):
        self.client = client
        self.owner_number = owner_number
        self.caller_id = caller_id

    def call(self, number: str, name: str) -> None:
        twiml = (
            "<Response>"
            f"<Say>Connecting you to {escape(name)}.</Say>"
            f'<Dial callerId="{escape(self.caller_id)}">{escape(number)}</Dial>'
            "</Response>"
        )
        self.client.calls.create(to=self.owner_number, from_=self.caller_id, twiml=twiml)
