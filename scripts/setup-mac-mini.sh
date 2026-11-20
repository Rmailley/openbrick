#!/usr/bin/env bash
# Prepares a spare Mac (built for a Late 2014 Mac mini on macOS Monterey) to run openBrick unattended.
# Run from the openbrick folder, after copying config.yaml into it:
#
#   scripts/setup-mac-mini.sh
#
# It sets power options, installs openBrick into a virtualenv, and starts it at login. It cannot sign in to
# your Apple ID, set up BlueBubbles, or turn on automatic login for you; it prints those steps at the end.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"

say() { printf '\n== %s\n' "$*"; }

say "Checking this Mac"
echo "macOS $(sw_vers -productVersion) on $(uname -m)"

# openBrick needs Python 3.11+. Homebrew barely supports Monterey, so use the python.org installer.
PYTHON=""
for candidate in python3.13 python3.12 python3.11 python3; do
  if command -v "$candidate" >/dev/null && "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null; then
    PYTHON="$(command -v "$candidate")"
    break
  fi
done
if [[ -z "$PYTHON" ]]; then
  echo "Python 3.11 or newer wasn't found." >&2
  echo "Install it from https://www.python.org/downloads/macos/ (the universal installer), then rerun this script." >&2
  exit 1
fi
echo "Using $("$PYTHON" --version) at $PYTHON"

[[ -f config.yaml ]] || { echo "Copy your config.yaml into $REPO first." >&2; exit 1; }
chmod 600 config.yaml

say "Power: never sleep, and start again after a power failure (needs your password)"
sudo pmset -a sleep 0 disksleep 0 displaysleep 10 autorestart 1 womp 1
pmset -g | grep -E "^ (sleep|disksleep|displaysleep|autorestart|womp)" || true

say "Remote login (SSH), so you can run this Mac without a monitor"
if ! sudo systemsetup -setremotelogin on 2>/dev/null; then
  echo "Couldn't enable it from here. Turn it on in System Settings > General > Sharing > Remote Login."
fi

say "Installing openBrick"
[[ -d .venv ]] || "$PYTHON" -m venv .venv
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -e '.[claude,twilio]'

say "Running the tests"
.venv/bin/pip install --quiet -e '.[dev]'
.venv/bin/pytest -q

say "Starting openBrick at login"
scripts/install-mac-services.sh --no-llm
sleep 3
if lsof -ti tcp:8787 -sTCP:LISTEN >/dev/null; then
  echo "openBrick is listening on 127.0.0.1:8787. Logs: ~/Library/Logs/openbrick.log"
else
  echo "openBrick isn't listening yet. Check ~/Library/Logs/openbrick.log" >&2
fi

cat <<'EOF'

== Still to do by hand
1. Messages > Settings > iMessage: sign in with your Apple ID, tick your phone number under
   "You can be reached at", and set "Start new conversations from" to your number.
2. System Settings > Apple ID > iCloud: turn on Contacts.
3. System Settings > Users & Groups: turn on automatic login (FileVault must be off), so iMessage
   runs again after a restart.
4. Install BlueBubbles Server (bluebubbles.app). Set a new password and put it in config.yaml, grant
   Contacts, Full Disk Access and Automation (Messages), and turn on "Start on login". Turn off its
   proxy service, since openBrick only talks to 127.0.0.1.
5. BlueBubbles Server > API & Webhooks: add a "New Messages" webhook pointing at
   http://127.0.0.1:8787/bluebubbles?token=<webhook_token from config.yaml>
6. iPhone: Settings > Messages > Text Message Forwarding: turn on this Mac.
7. Stop openBrick on your old Mac first (scripts/install-mac-services.sh --uninstall), so only one
   machine forwards messages.
8. From the dumbphone, text "help" to your main number.
EOF
