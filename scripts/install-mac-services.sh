#!/usr/bin/env bash
# Makes openBrick and its typo-fixing model start at login on a Mac and restart if they crash.
# Run from the openbrick folder after creating config.yaml:
#
#   scripts/install-mac-services.sh            # openBrick + llama-server (small Qwen model)
#   scripts/install-mac-services.sh --no-llm   # openBrick only
#
# Logs go to ~/Library/Logs/openbrick.log and ~/Library/Logs/openbrick-llm.log.
# To remove: scripts/install-mac-services.sh --uninstall
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
AGENTS="${LAUNCH_AGENTS_DIR:-$HOME/Library/LaunchAgents}"
LOGS="$HOME/Library/Logs"
MODEL="${OPENBRICK_MODEL:-Qwen/Qwen2.5-3B-Instruct-GGUF:Q4_K_M}"
PORT="${OPENBRICK_LLM_PORT:-8081}"

uninstall() {
  for label in com.openbrick.server com.openbrick.llm; do
    launchctl bootout "gui/$(id -u)/$label" 2>/dev/null || true
    rm -f "$AGENTS/$label.plist"
  done
}

load() {
  [[ -n "${NO_LOAD:-}" ]] && return
  launchctl bootout "gui/$(id -u)/$1" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$AGENTS/$1.plist"
}

# Writes a launchd agent that runs a command at login and restarts it whenever it exits.
write_agent() {
  local label="$1" log="$2"; shift 2
  local args=""
  for arg in "$@"; do args+="    <string>$arg</string>"$'\n'; done
  cat > "$AGENTS/$label.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$label</string>
  <key>ProgramArguments</key>
  <array>
$args  </array>
  <key>WorkingDirectory</key>
  <string>$REPO</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>ThrottleInterval</key>
  <integer>10</integer>
  <key>StandardOutPath</key>
  <string>$log</string>
  <key>StandardErrorPath</key>
  <string>$log</string>
</dict>
</plist>
EOF
}

if [[ "${1:-}" == "--uninstall" ]]; then
  uninstall
  echo "Removed openBrick startup services."
  exit 0
fi

[[ -f "$REPO/config.yaml" ]] || { echo "Create $REPO/config.yaml first (copy config.example.yaml)." >&2; exit 1; }
[[ -x "$REPO/.venv/bin/openbrick" ]] || { echo "Install openBrick first: python3 -m venv .venv && .venv/bin/pip install -e ." >&2; exit 1; }
mkdir -p "$AGENTS" "$LOGS"

write_agent com.openbrick.server "$LOGS/openbrick.log" "$REPO/.venv/bin/openbrick" "$REPO/config.yaml"
load com.openbrick.server
echo "openBrick will start at login."

if [[ "${1:-}" != "--no-llm" ]]; then
  LLAMA="$(command -v llama-server || true)"
  [[ -n "$LLAMA" ]] || { echo "llama-server not found. Install it with: brew install llama.cpp" >&2; exit 1; }
  # -hf downloads the model once (about 2 GB) and reuses it after that.
  write_agent com.openbrick.llm "$LOGS/openbrick-llm.log" \
    "$LLAMA" -hf "$MODEL" --host 127.0.0.1 --port "$PORT" -c 4096
  load com.openbrick.llm
  echo "llama-server ($MODEL) will start at login on port $PORT. The first start downloads the model."
fi
