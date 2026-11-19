from dataclasses import dataclass
from pathlib import Path

import yaml

TRANSPORTS = ("relay", "twilio")


@dataclass
class TwilioConfig:
    account_sid: str
    auth_token: str
    number: str


@dataclass
class BlueBubblesConfig:
    url: str
    password: str
    webhook_token: str


@dataclass
class TwoFAConfig:
    pin: str
    accounts: dict[str, str]


@dataclass
class Config:
    transport: str
    owner_number: str
    bluebubbles: BlueBubblesConfig | None
    twilio: TwilioConfig | None
    public_url: str | None
    twofa: TwoFAConfig | None
    contacts: dict[str, str]
    data_dir: Path
    host: str = "127.0.0.1"
    port: int = 8787


def load(path: str | Path) -> Config:
    raw = yaml.safe_load(Path(path).read_text())

    transport = raw.get("transport", "relay")
    if transport not in TRANSPORTS:
        raise ValueError(f"transport must be one of {', '.join(TRANSPORTS)}, not {transport!r}")
    if transport == "relay" and not raw.get("bluebubbles"):
        raise ValueError("transport: relay needs a bluebubbles section (your Mac relays the texts)")
    if transport == "twilio" and not (raw.get("twilio") and raw.get("public_url")):
        raise ValueError("transport: twilio needs a twilio section and public_url")

    twofa = None
    if tf := raw.get("twofa"):
        # YAML turns an unquoted 0421 into the integer 421, silently changing the PIN.
        if not isinstance(tf.get("pin"), str):
            raise ValueError("twofa.pin must be a quoted string in config.yaml, e.g. pin: \"0421\"")
        twofa = TwoFAConfig(
            pin=tf["pin"],
            accounts={k.lower(): str(v).replace(" ", "") for k, v in (tf.get("accounts") or {}).items()},
        )

    bb = raw.get("bluebubbles")
    tw = raw.get("twilio")
    return Config(
        transport=transport,
        owner_number=str(raw["owner_number"]),
        bluebubbles=BlueBubblesConfig(**bb) if bb else None,
        twilio=TwilioConfig(**tw) if tw else None,
        public_url=str(raw["public_url"]).rstrip("/") if raw.get("public_url") else None,
        twofa=twofa,
        contacts={k.lower(): str(v) for k, v in (raw.get("contacts") or {}).items()},
        data_dir=Path(raw.get("data_dir", "./data")),
        host=raw.get("host", "127.0.0.1"),
        port=int(raw.get("port", 8787)),
    )
