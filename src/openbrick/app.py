import hmac

from flask import Flask, Response, abort, request

from .config import Config
from .contacts import ContactBook
from .directions import Directions, Geocoder, TripPlanner
from .imessage import BlueBubbles, format_incoming, incoming_message, sender
from .llm import Interpreter
from .router import Router
from .sms import RelaySMS, TwilioSMS
from .state import State
from .twofa import TwoFA


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
    interpreter = Interpreter(config.llm.url, config.llm.model) if config.llm else None
    book = ContactBook(config.contacts, fetch=imessage.contacts if imessage else None)
    router = Router(book, state, imessage=imessage, twofa=twofa, directions=directions, interpreter=interpreter)

    app = Flask(__name__)

    if config.bluebubbles:
        token = config.bluebubbles.webhook_token

        @app.post("/bluebubbles")
        def bluebubbles_webhook():
            if not hmac.compare_digest(request.args.get("token", ""), token):
                abort(403)
            msg = incoming_message(request.get_json(silent=True) or {})
            if msg is None:
                return "", 204

            if sender(msg) == config.owner_number:
                # The dumbphone texting your main number is a command. Over Twilio, commands arrive at /sms instead.
                if config.transport == "relay":
                    state.set("owner_chat", msg["chats"][0]["guid"])
                    reply = router.handle(msg.get("text") or "")
                    if reply:
                        sms.send(reply)
                return "", 204

            if result := format_incoming(msg, book.label):
                chat_guid, text = result
                state.set("last_chat", chat_guid)
                sms.send(text)
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
                reply = router.handle(request.form.get("Body", ""))
                if reply:
                    resp.message(reply)
            return Response(str(resp), mimetype="application/xml")

    return app
