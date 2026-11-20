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
| `@henry on my way` or `to henry on my way` | Sends an iMessage to someone in your contacts. First name, full name, last name or nickname all work. |
| `@+15550001111 hi` / `@sam@icloud.com hi` | Sends an iMessage to a number or Apple ID |
| `go home to union station` | Texts back transit directions, leaving now ([setup](#transit-directions)) |
| `2fa 0421 github` | Texts back the current code for that account |
| `2fa 0421` | Lists your 2FA accounts |
| `help` | Lists commands |

Only texts from the dumbphone's number (`owner_number`) count as commands. Everything else is forwarded to you.

**Contacts come from your iPhone.** openBrick reads the Mac's Contacts app through BlueBubbles, and the Mac gets them from your iPhone over iCloud. New contacts show up within minutes. Incoming messages show the sender's first name, like `[Henry] running late?`, or the full name when two people share it. For extra short names like `mom`, add them under `contacts:` in `config.yaml`. They take priority over the address book.

**Names don't have to be exact:**

| You text | openBrick |
|---|---|
| `@henry see you soon` | Sends to Henry right away, if he's your only Henry |
| `@mike see you at 8` | `Which mike? 1 Mike Chen 2 Mike Ross. Reply a number.` |
| `@mike chen see you at 8` | Sends to Mike Chen |
| `@henny running late` | `Send to Henry Lee: "running late"? Reply y to send.` |

A corrected name never sends without your `y`. With the optional [typo fixing](#typo-fixing) turned on, even garbled commands like `dir hom 2 union statoin` and `txt sam running late` work.

## Setup

### 1. iPhone

- **Settings → Messages → Text Message Forwarding:** turn on your Mac. This lets the Mac send and receive green-bubble texts through the iPhone.
- **Calls:** Settings → Phone → Call Forwarding → the dumbphone's number. On Verizon, dial `*72` followed by the dumbphone's number instead. Calls to your main number then ring the dumbphone. Turn it off when you take the iPhone out again.
- Keep it plugged in and on Wi-Fi. Turn off any Focus mode that would stop it relaying.

### 2. Mac

- **Messages → Settings → iMessage:** check your phone number under "You can be reached at," and set "Start new conversations from" to your phone number. Your messages then come from your number, not your email.
- Install [BlueBubbles Server](https://bluebubbles.app), set a password, and grant the permissions it asks for, including **Contacts**.
- **System Settings → [your name] → iCloud:** turn on Contacts, so the Mac has your iPhone's contacts.
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

To keep openBrick running, start it at login and restart it after any crash:

```bash
scripts/install-mac-services.sh            # openBrick + typo-fixing model
scripts/install-mac-services.sh --no-llm   # openBrick only
```

Logs are in `~/Library/Logs/openbrick.log`. Remove the services with `--uninstall`. Also turn on "Start on login" in BlueBubbles Server's settings.

### 4. Try it

From the dumbphone, text `help` to your main number. The reply arrives in the same conversation. Then ask someone to iMessage you.

On the iPhone you'll see a conversation with the dumbphone's number that holds everything openBrick relayed. That's expected.

### Using a MacBook

A spare MacBook works well, but it has to stay awake and survive restarts:

- **No sleep on power:** System Settings → Battery → Options → "Prevent automatic sleeping on power adapter when the display is off," or `sudo pmset -c sleep 0 disksleep 0 displaysleep 5`.
- **Lid:** leave it open with the screen off. Closing the lid sleeps a MacBook. `sudo pmset -a disablesleep 1` keeps it awake closed (undo with `0`), but it runs hotter. Keep it on a hard surface.
- **Battery:** leave Optimized Battery Charging on, or cap charging with [AlDente](https://apphousekitchen.com). A battery plugged in for years can swell, so check now and then that the trackpad and case aren't bulging.
- **Restarts:** iMessage only runs while you're logged in, so turn on automatic login (System Settings → Users & Groups). That requires FileVault off, which leaves the disk readable if the laptop is stolen. Keep FileVault on if you'd rather log in by hand after updates.

## What to expect

- **If the iPhone is off or offline,** green-bubble texts stop relaying. Calls and texts to the dumbphone's own number still work, and so do iMessages, as long as the Mac is up.
- **When you call someone from the dumbphone,** they see the dumbphone's number, not your main one (see the roadmap).
- **`@name` sends as iMessage.** For friends without iPhones, wait for them to text you and use `r`.
- **Photos** arrive as `(sent an attachment)`. Check them on the iPhone later.
- **Sending green-bubble texts through BlueBubbles** relies on Text Message Forwarding. It hasn't been tested across every macOS version yet. If replies to Android friends fail, please open an issue with your macOS version.

## Transit directions

`go home to union station` texts back something like:

```
Leave 2:10pm, arrive 2:41pm (31 min)
Walk 5 min to Dupont Circle
2:19pm Metro RED toward Glenmont. Off at Union Station 2:29pm
Walk 2 min to union station
```

Routes come from [OpenTripPlanner](https://www.opentripplanner.org), an open-source trip planner you run yourself, using your transit agency's published schedules and live arrival times. Places are looked up with OpenStreetMap's free [Nominatim](https://nominatim.org) service, limited to your area by `viewbox`. Save the places you use often under `directions.places` so `home` and `work` just work.

You need [Docker](https://docs.docker.com/get-docker/) and about 3 GB of free memory. If your old Mac can't run Docker, run OpenTripPlanner on another machine at home and point `otp_url` at it.

**Washington, DC** has a script:

1. Get a free API key at [developer.wmata.com](https://developer.wmata.com) (sign up, then subscribe to the Default Tier).
2. Run `WMATA_API_KEY=yourkey scripts/setup-otp-dc.sh`. It downloads DC's street map and WMATA's bus and rail schedules, then builds the planner.
3. Run the `docker run` command it prints, and add the `directions` section to `config.yaml`.
4. Rerun the script weekly, for example from cron, so schedule changes are picked up.

The DC street map covers the District only. For trips into Maryland or Virginia, add those states' maps from [Geofabrik](https://download.geofabrik.de/north-america/us.html) to the data folder and raise `OTP_MEMORY` to `8g` or more.

**Other cities** work the same way. Put your area's OpenStreetMap extract (`.osm.pbf`) and your agency's GTFS schedules (a `.zip` with `gtfs` in the file name) in one folder, then build with the same `docker run ... --build --save` command the script uses. The [Mobility Database](https://mobilitydatabase.org) lists GTFS feeds for most agencies.

## Typo fixing

Keypads make typos easy. When a text doesn't match any command, openBrick checks it against the words it knows, using edit distance (one slip is one edit: a wrong, missing, extra or swapped letter). It's built in, always on, and needs no model, so it runs fine on an old Mac.

| You text | openBrick runs |
|---|---|
| `rply see u soon` | `r see u soon` (after you reply `y`) |
| `txt sam running late` | `@sam running late` (after you reply `y`) |
| `dirctions hom 2 union statoin` | `go home to union statoin` |
| `2fa1234 gogle` | `2fa 1234 google` |
| `hepl` | `help` |

It fixes command words, the names of your saved places and 2FA accounts, and (through the contact matcher) names in your address book. It never changes the text of a message. Short words must be exact, so ordinary sentences such as `did you go to the store` aren't mistaken for commands. Anything that would send a message after a correction waits for your `y`, and directions show the command openBrick understood, e.g. `(go home to union station)`. Unknown places aren't spell-checked, since openBrick has no dictionary of them.

### Optional: a local model for harder cases

For texts the spellchecker can't fix, openBrick can also ask a small AI model running on your own machine. It needs a few GB of free memory, so skip it on a small Mac. The model only ever sees your own commands, never messages people send you.

It runs a small Qwen model (Qwen2.5 3B Instruct, about 2 GB) on [llama.cpp](https://github.com/ggml-org/llama.cpp):

1. Install llama.cpp with `brew install llama.cpp`.
2. Add the `llm` section to `config.yaml`.
3. Run `scripts/install-mac-services.sh`. It starts `llama-server` on port 8081 at login and downloads the model the first time.

To use a different model, set `OPENBRICK_MODEL` to another Hugging Face GGUF before running the script, e.g. `OPENBRICK_MODEL=Qwen/Qwen2.5-1.5B-Instruct-GGUF:Q4_K_M` for a faster, less accurate one on an older Mac. Already use [Ollama](https://ollama.com)? Point `llm.url` at `http://127.0.0.1:11434` and set `model` to an Ollama model name.

The same safeguards apply: your words are sent as typed, sends wait for a yes, directions show what was searched, and unclear texts get the plain "Unknown command" reply.

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
- **Spotify.** `play radiohead` controls your Spotify Connect speakers at home.
- **Rides (experimental).** `uber me from home to the airport` gets an estimate, then `YES` to book. Uber and Lyft have no public API for booking your own rides, so this would automate their website. It's fragile, against their terms, and could get your account flagged. Opt-in only.

Instagram is not on the roadmap.

## Development

```bash
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest
```

New commands go in `src/openbrick/router.py`. If a command can be typo'd, also add its verb to `VERBS` in `src/openbrick/typo.py` (and `llm.py` if you use the model). Keep replies short, since every reply is read on a 2-inch screen.

## License

MIT
