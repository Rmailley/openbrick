import os
from dataclasses import dataclass, field
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
class DirectionsConfig:
    otp_url: str = "http://127.0.0.1:8080"
    geocoder_url: str = "https://nominatim.openstreetmap.org"
    viewbox: str | None = None
    places: dict[str, str] = field(default_factory=dict)


@dataclass
class LLMConfig:
    url: str = "http://127.0.0.1:8081"
    model: str = "qwen"


@dataclass
class AnthropicConfig:
    api_key: str | None = None  # None: use ANTHROPIC_API_KEY or `ant auth login`
    model: str = "claude-opus-5-5"
    summaries: bool = True  # send muted group messages to Claude to summarize them


@dataclass
class CallsConfig:
    account_sid: str
    auth_token: str
    caller_id: str  # your main number, verified in Twilio


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
    directions: DirectionsConfig | None = None
    llm: LLMConfig | None = None
    anthropic: AnthropicConfig | None = None
    calls: CallsConfig | None = None
    host: str = "127.0.0.1"
    port: int = 8787


def load_env(path: str | Path) -> None:
    """Put KEY=value lines from a .env file into the environment, without overriding what's already set.

    This is how the launchd service gets ANTHROPIC_API_KEY, since it doesn't inherit your shell's variables.
    """
    path = Path(path)
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip().strip("\"'")
        if key.strip().removeprefix("export ").strip() and value:
            os.environ.setdefault(key.strip().removeprefix("export ").strip(), value)


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

    directions = None
    if (d := raw.get("directions")) is not None:
        d = dict(d or {})
        d["places"] = {k.lower(): str(v) for k, v in (d.get("places") or {}).items()}
        directions = DirectionsConfig(**d)

    bb = raw.get("bluebubbles")
    tw = raw.get("twilio")
    llm = raw.get("llm")
    claude = raw.get("anthropic")
    calls = raw.get("calls")
    return Config(
        transport=transport,
        owner_number=str(raw["owner_number"]),
        bluebubbles=BlueBubblesConfig(**bb) if bb else None,
        twilio=TwilioConfig(**tw) if tw else None,
        public_url=str(raw["public_url"]).rstrip("/") if raw.get("public_url") else None,
        twofa=twofa,
        contacts={k.lower(): str(v) for k, v in (raw.get("contacts") or {}).items()},
        data_dir=Path(raw.get("data_dir", "./data")),
        directions=directions,
        llm=LLMConfig(**llm) if llm is not None else None,
        anthropic=AnthropicConfig(**claude) if claude is not None else None,
        calls=CallsConfig(**calls) if calls else None,
        host=raw.get("host", "127.0.0.1"),
        port=int(raw.get("port", 8787)),
    )
