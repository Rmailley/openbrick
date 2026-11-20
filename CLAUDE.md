# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'   # dev extra adds pytest + twilio
.venv/bin/pytest                                             # all tests
.venv/bin/pytest tests/test_router.py::test_name             # single test
cp config.example.yaml config.yaml && .venv/bin/openbrick config.yaml   # run (serves on 127.0.0.1:8787)
```

No linter is configured. `scripts/install-mac-services.sh` installs launchd services (`--no-llm`, `--uninstall`); `scripts/setup-otp-dc.sh` builds the OpenTripPlanner graph for DC.

## Architecture

openBrick relays iMessages/texts from a Mac (running BlueBubbles Server) to a dumbphone via SMS sent from the user's own main number, and treats SMS from the dumbphone (`owner_number`) as commands. Flask app served by waitress; `create_app` in `src/openbrick/app.py` wires everything together.

Two message directions, both entering through webhooks:

- **Incoming from others** → BlueBubbles `POST /bluebubbles?token=` → `imessage.incoming_message`/`format_incoming` (labels sender via `ContactBook.label`) → `sms.send`. The chat GUID is saved as `last_chat` in `State` so `r <msg>` replies to it.
- **Commands from the owner** → same BlueBubbles webhook when `sender(msg) == owner_number` (transport `relay`), or `POST /sms` (transport `twilio`, signature-validated against `public_url`) → `Router.handle` → reply text sent back over `sms`.

Key pieces:

- `router.py`: regex-based command parsing (`r`, `@name`/`to name`, `go A to B`, `2fa`, `help`). Raises `Unresolved` with the user-facing message. Multi-turn flows (pick a number among ambiguous contacts, `y` to confirm a fuzzy-corrected name) are stored as `pending` in `State` and checked first on the next message. Unmatched text falls through to the interpreter chain (`Spellchecker`, then the optional model).
- `typo.py`: built-in, always-on typo fixer (Damerau-Levenshtein against command verbs, saved places and 2FA accounts). Same `interpret(text, known) -> command | None` interface as `llm.py`; `app.py` chains it ahead of the optional model with `Fallback`.
- `llm.py`: optional typo fixer calling a local llama.cpp server (Qwen) with a JSON schema; only ever sees the owner's commands, never incoming messages. Its output is mapped back onto the same router actions.
- `contacts.py`: `ContactBook` merges `contacts:` from config (priority) with the address book fetched via BlueBubbles (`imessage.contacts`); handles fuzzy and ambiguous matches.
- `sms.py`: two transports behind one `.send()` interface — `RelaySMS` (sends via BlueBubbles into the owner chat tracked as `owner_chat` in State) and `TwilioSMS` (twilio is an optional dependency, imported lazily).
- `directions.py`: `Geocoder` (Nominatim, bounded by `viewbox`) + `TripPlanner` (self-hosted OpenTripPlanner) + `Directions` formatter; raises `PlaceNotFound`.
- `twofa.py`: PIN-gated TOTP codes via pyotp. `state.py`: tiny JSON file store in `data_dir`, rewritten on every `set`.
- `config.py`: loads `config.yaml` (see `config.example.yaml`); optional sections (`bluebubbles`, `twilio`, `twofa`, `directions`, `llm`, `contacts`) enable features when present.

Tests in `tests/` mirror the modules and use fake `sms`/`imessage` objects passed into `create_app`/`Router` rather than hitting the network.
