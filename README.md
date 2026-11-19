# openBrick

Leave your iPhone at home. Carry a dumbphone. Keep your messages.

openBrick is a small open-source server that turns any phone that can send texts into a companion for your iPhone. Your iPhone stays in a drawer with your main number. Your old Mac relays your iMessages and texts to the dumbphone, and sends your replies from your main number, so nobody needs a new number for you. There's no feed to scroll, because SMS can't carry one.

It's an open, bring-your-own-plan take on services like Dumb Co, built to work on phones too basic to install apps (the reference phone is an Alcatel 1041: 64 MB of RAM, closed firmware).

```
  Mom's iPhone ──iMessage──▶ your number ──▶ Mac (BlueBubbles) ──▶ openBrick
                                                     │                 │
  Alcatel ◀──── SMS from your main number ◀── iPhone ◀── "[mom] dinner?"
     │
     └── SMS "r yes" to your main number ──▶ iPhone ──▶ Mac ──▶ openBrick ──▶ iMessage to Mom
```

## How it works

You need three things:

- **Your iPhone:** keeps your main number. Stays at home, charged, on Wi-Fi.
- **The dumbphone:** its own SIM, on any cheap plan.
- **A Mac:** signed in to the same Apple ID, running [BlueBubbles Server](https://bluebubbles.app) and openBrick. An old Mac is fine. It has to stay on.

What happens in practice:

| Someone... | What happens |
|---|---|
| iMessages your main number | The Mac gets it. The dumbphone gets `[mom] dinner?` from your main number. |
| Texts your main number (green bubble) | The same, through the iPhone's Text Message Forwarding |
| Sends you a login code by SMS | Forwarded to the dumbphone like any other text |
| Calls your main number | Rings the dumbphone, if you set up call forwarding (below) |

You control it by texting **your own main number** from the dumbphone:

| Text | What happens |
|---|---|
| `r sounds good` | Replies to whoever messaged you last, from your main number. Works for group chats and green-bubble friends. |
| `@mom on my way` or `to mom on my way` | Sends an iMessage to a contact from `config.yaml` |
| `@+15550001111 hi` / `@sam@icloud.com hi` | Sends an iMessage to a number or Apple ID |
| `2fa 0421 github` | Texts back the current code for that account |
| `2fa 0421` | Lists your 2FA accounts |
| `help` | Lists commands |

Only texts from the dumbphone's number (`owner_number`) count as commands. Everything else is forwarded to you.

## Setup

### 1. iPhone

- **Settings → Messages → Text Message Forwarding:** turn on your Mac. This lets the Mac send and receive green-bubble texts through the iPhone.
- **Calls:** Settings → Phone → Call Forwarding → the dumbphone's number. On Verizon, dial `*72` followed by the dumbphone's number instead. Calls to your main number then ring the dumbphone. Turn it off when you take the iPhone out again.
- Keep it plugged in and on Wi-Fi. Turn off any Focus mode that would stop it relaying.

### 2. Mac

- **Messages → Settings → iMessage:** check your phone number under "You can be reached at," and set "Start new conversations from" to your phone number. Your messages then come from your number, not your email.
- Install [BlueBubbles Server](https://bluebubbles.app), set a password, and grant the permissions it asks for.
- **System Settings → Energy:** stop the Mac from sleeping.

### 3. openBrick (on the same Mac)

```bash
git clone <this repo> openbrick && cd openbrick
python3 -m venv .venv && .venv/bin/pip install -e .
cp config.example.yaml config.yaml   # then fill it in
chmod 600 config.yaml
.venv/bin/openbrick config.yaml
```

In BlueBubbles Server → API & Webhooks, add a webhook for **New Messages** pointing at `http://127.0.0.1:8787/bluebubbles?token=<webhook_token>`.

### 4. Try it

From the dumbphone, text `help` to your main number. The reply arrives in the same conversation. Then ask someone to iMessage you.

On the iPhone you'll see a conversation with the dumbphone's number that holds everything openBrick relayed. That's expected.

## What to expect

- **If the iPhone is off or offline,** green-bubble texts stop relaying. Calls and texts to the dumbphone's own number still work, and so do iMessages, as long as the Mac is up.
- **When you call someone from the dumbphone,** they see the dumbphone's number, not your main one (see the roadmap).
- **`@name` sends as iMessage.** For friends without iPhones, wait for them to text you and use `r`.
- **Photos** arrive as `(sent an attachment)`. Check them on the iPhone later.
- **Sending green-bubble texts through BlueBubbles** relies on Text Message Forwarding. It hasn't been tested across every macOS version yet. If replies to Android friends fail, please open an issue with your macOS version.

## No iPhone? Use Twilio instead

Set `transport: twilio` and fill in the `twilio` section of the config. Commands then go to a Twilio number (about $1/month plus a cent or so per text) instead of your own. The Mac still relays iMessages sent to your Apple ID email, but not to your phone number, which Apple only lets an iPhone register.

Extra setup:

```bash
.venv/bin/pip install -e '.[twilio]'
```

- US Twilio numbers need A2P 10DLC registration before they can text you. Register as a sole proprietor in the Twilio console. It takes a few days.
- Twilio needs a public HTTPS address: [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/) or [Tailscale Funnel](https://tailscale.com/kb/1223/funnel) pointed at port 8787. Put the URL in `public_url`, and set the Twilio number's incoming-message webhook to `<public_url>/sms`.
- If your number was on an iPhone before, deregister it at [selfsolve.apple.com/deregister-imessage](https://selfsolve.apple.com/deregister-imessage). Otherwise iPhone users' messages to your number go nowhere.

## Running on another machine

openBrick can run on Linux or Windows (WSL) while BlueBubbles stays on the Mac. Point `bluebubbles.url` at the Mac's address on your network, set `host: "0.0.0.0"`, and point the BlueBubbles webhook at that machine. On WSL:

- WSL2 sits behind NAT, so the Mac can't reach it by default. On Windows 11, add `networkingMode=mirrored` under `[wsl2]` in `%UserProfile%\.wslconfig`, then run `wsl --shutdown`. Allow port 8787 through Windows Firewall.
- WSL stops when no terminal is open. Enable systemd in `/etc/wsl.conf`, run openBrick as a systemd service, and start WSL at login with Task Scheduler.

Since the Mac has to stay on anyway, running everything on it is simpler.

## Security

- The BlueBubbles webhook needs `webhook_token`. BlueBubbles doesn't sign its webhooks, so keep port 8787 off the internet.
- In Twilio mode, requests are checked against Twilio's signature, using `public_url`.
- SMS isn't encrypted, and caller ID can be spoofed. That's why 2FA needs a PIN and locks for 15 minutes after 5 wrong tries. SMS-delivered codes are still weaker than a 2FA app, so keep banking, email and your Apple ID off the list.
- `config.yaml` holds every secret. It's in `.gitignore`. Keep it that way.

## Roadmap

- **Calls from your main number.** `call mom` would have Twilio ring the dumbphone, then connect you to Mom showing your main number as caller ID. Twilio allows this once you verify you own the number.
- **Directions.** `directions to 123 Main St` gets the steps back by text.
- **Spotify.** `play radiohead` controls your Spotify Connect speakers at home.
- **Rides (experimental).** `uber me from home to the airport` gets an estimate, then `YES` to book. Uber and Lyft have no public API for booking your own rides, so this would automate their website. It's fragile, against their terms, and could get your account flagged. Opt-in only.

Instagram is not on the roadmap.

## Development

```bash
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest
```

New commands go in `src/openbrick/router.py`. Keep replies short, since every reply is read on a 2-inch screen.

## License

MIT
