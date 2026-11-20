import hmac
import logging

from flask import Flask, Response, abort, request

from .config import Config
from .contacts import ContactBook
from .directions import Directions, Geocoder, TripPlanner
from .health import Stats, report
from .imessage import BlueBubbles, describe, describe_incoming, incoming_message, sender
from .llm import Interpreter
from .mute import Mutes
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
    book = ContactBook(config.contacts, fetch=imessage.contacts if imessage else None)

    # The spellchecker is free and always on. Whatever it can't fix goes to Claude if you've set up an
    # Anthropic account, else to a local llama.cpp model if you run one.
    model, summarizer, caller = None, None, None
    if a := config.anthropic:
        import anthropic

        from .claude import ClaudeInterpreter, ClaudeSummarizer

        client = anthropic.Anthropic(api_key=a.api_key) if a.api_key else anthropic.Anthropic()
        model = ClaudeInterpreter(client, a.model)
        summarizer = ClaudeSummarizer(client, a.model) if a.summaries else None
    elif config.llm:
        model = Interpreter(config.llm.url, config.llm.model)
    interpreter = Fallback(Spellchecker(), *([model] if model else []))

    if c := config.calls:
        from twilio.rest import Client

        from .calls import Caller

        caller = Caller(Client(c.account_sid, c.auth_token), config.owner_number, c.caller_id)

    mutes = Mutes(state, summarizer)
    stats = Stats()
    router = Router(
        book, state, imessage=imessage, twofa=twofa, directions=directions, interpreter=interpreter,
        caller=caller, mutes=mutes,
    )

    app = Flask(__name__)

    def _deliver(text: str, what: str) -> bool:
        # A 500 would make BlueBubbles retry the webhook, which duplicates messages once sending recovers.
        try:
            sms.send(text)
            return True
        except Exception as e:
            stats.count("send_failed")
            log.error("%s failed: %s", what, describe(e))
            return False

    def sweep() -> None:
        """Send the summary for every group mute that has run out."""
        for text in mutes.sweep():
            _deliver(text, "mute summary")

    app.config["sweep"] = sweep  # __main__ calls this once a minute

    def health() -> None:
        healthy, line = report(stats, imessage)
        (log.info if healthy else log.warning)(line)

    app.config["health"] = health  # __main__ calls this once an hour

    if config.bluebubbles:
        token = config.bluebubbles.webhook_token

        @app.post("/bluebubbles")
        def bluebubbles_webhook():
            if not hmac.compare_digest(request.args.get("token", ""), token):
                log.warning("webhook rejected: bad token")
                abort(403)
            stats.webhook()
            sweep()
            msg = incoming_message(request.get_json(silent=True) or {})
            if msg is None:
                return "", 204

            if sender(msg) == config.owner_number:
                # The dumbphone texting your main number is a command. Over Twilio, commands arrive at /sms instead.
                if config.transport == "relay":
                    state.set("owner_chat", msg["chats"][0]["guid"])
                    log.info("command from owner")
                    stats.count("commands")
                    reply = router.handle(msg.get("text") or "")
                    if reply:
                        if _deliver(reply, "reply to owner"):
                            log.info("replied to owner")
                return "", 204

            if d := describe_incoming(msg, book.label):
                chat_guid, who, group, text = d
                if group and (state.get("chat_names") or {}).get(chat_guid) != group:
                    state.set("chat_names", {**(state.get("chat_names") or {}), chat_guid: group})
                if mutes.is_muted(chat_guid):
                    # Held for the summary. It doesn't become "last chat", so `r` still goes where it did.
                    mutes.hold(chat_guid, who, text)
                    log.info("held a message in a muted group")
                    return "", 204
                state.set("last_chat", chat_guid)
                line = f"[{who} in {group}] {text}" if group else f"[{who}] {text}"
                if _deliver(line, f"forward from {who}"):
                    stats.count("forwarded")
                    log.info("forwarded message from %s", who)
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

            sweep()
            resp = MessagingResponse()
            if request.form.get("From") == config.owner_number:
                log.info("command from owner")
                reply = router.handle(request.form.get("Body", ""))
                if reply:
                    resp.message(reply)
                    log.info("replied to owner")
            return Response(str(resp), mimetype="application/xml")

    return app
