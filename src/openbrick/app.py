import hmac
import logging

from flask import Flask, Response, abort, request

from .config import Config
from .contacts import ContactBook
from .directions import Directions, Geocoder, TripPlanner
from .imessage import BlueBubbles, describe, format_incoming, incoming_message, sender
from .llm import Interpreter
from .router import Router
from .sms import RelaySMS, TwilioSMS
from .state import State
from .typo import Fallback, Spellchecker
from .twofa import TwoFA

log = logging.getLogger("openbrick.app")


def create_app(config: Config, sms=None, imessage=None) -> Flask:
    state = State(config.data_dir / "state.json")
    if imessage is None and config.bluebubbles:
        imessage = BlueBubbles(config.bluebubbles.url, config.bluebubbles.password)
    if sms is None:
        if config.transport == "relay":
            sms = RelaySMS(imessage, state, config.owner_number)
        else:
            from twilio.rest import Client

            sms = TwilioSMS(
                Client(config.twilio.account_sid, config.twilio.auth_token),
                config.twilio.number,
                config.owner_number,
            )
    twofa = TwoFA(config.twofa.pin, config.twofa.accounts) if config.twofa else None
    directions = None
    if d := config.directions:
        directions = Directions(Geocoder(d.geocoder_url, d.viewbox), TripPlanner(d.otp_url), d.places)
    # The spellchecker is free and always on; a local model, if configured, only gets what it can't fix.
    interpreter = Fallback(Spellchecker(), *([Interpreter(config.llm.url, config.llm.model)] if config.llm else []))
    book = ContactBook(config.contacts, fetch=imessage.contacts if imessage else None)
    router = Router(book, state, imessage=imessage, twofa=twofa, directions=directions, interpreter=interpreter)

    app = Flask(__name__)

    def _deliver(text: str, what: str) -> bool:
        # A 500 would make BlueBubbles retry the webhook, which duplicates messages once sending recovers.
        try:
            sms.send(text)
            return True
        except Exception as e:
            log.error("%s failed: %s", what, describe(e))
            return False

    if config.bluebubbles:
        token = config.bluebubbles.webhook_token

        @app.post("/bluebubbles")
        def bluebubbles_webhook():
            if not hmac.compare_digest(request.args.get("token", ""), token):
                log.warning("webhook rejected: bad token")
                abort(403)
            msg = incoming_message(request.get_json(silent=True) or {})
            if msg is None:
                return "", 204

            if sender(msg) == config.owner_number:
                # The dumbphone texting your main number is a command. Over Twilio, commands arrive at /sms instead.
                if config.transport == "relay":
                    state.set("owner_chat", msg["chats"][0]["guid"])
                    log.info("command from owner")
                    reply = router.handle(msg.get("text") or "")
                    if reply:
                        if _deliver(reply, "reply to owner"):
                            log.info("replied to owner")
                return "", 204

            if result := format_incoming(msg, book.label):
                chat_guid, text = result
                state.set("last_chat", chat_guid)
                if _deliver(text, f"forward from {book.label(sender(msg))}"):
                    log.info("forwarded message from %s", book.label(sender(msg)))
            return "", 204

    if config.transport == "twilio":
        from twilio.request_validator import RequestValidator
        from twilio.twiml.messaging_response import MessagingResponse

        validator = RequestValidator(config.twilio.auth_token)

        @app.post("/sms")
        def sms_webhook():
            # Twilio signs the public URL it called, not the local one behind the tunnel.
            url = config.public_url + request.full_path.rstrip("?")
            if not validator.validate(url, request.form, request.headers.get("X-Twilio-Signature", "")):
                abort(403)

            resp = MessagingResponse()
            if request.form.get("From") == config.owner_number:
                log.info("command from owner")
                reply = router.handle(request.form.get("Body", ""))
                if reply:
                    resp.message(reply)
                    log.info("replied to owner")
            return Response(str(resp), mimetype="application/xml")

    return app
