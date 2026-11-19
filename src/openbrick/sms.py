class TwilioSMS:
    def __init__(self, client, from_number: str, to_number: str):
        self.client = client
        self.from_number = from_number
        self.to_number = to_number

    def send(self, text: str) -> None:
        self.client.messages.create(from_=self.from_number, to=self.to_number, body=text)


class RelaySMS:
    """Texts the dumbphone from your own number, via the Mac and your iPhone's Text Message Forwarding."""

    def __init__(self, imessage, state, owner_number: str):
        self.imessage = imessage
        self.state = state
        self.owner_number = owner_number

    def send(self, text: str) -> None:
        chat = self.state.get("owner_chat") or f"SMS;-;{self.owner_number}"
        self.imessage.send_text(chat, text)
