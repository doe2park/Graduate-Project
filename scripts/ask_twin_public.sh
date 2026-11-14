#!/bin/sh
# Ask the twin, reachable from outside the Wi-Fi for a demo: the laptop stays the server (the API key never leaves it) and a
# Cloudflare quick tunnel gives it a temporary https address. Pages and API come from that one address, so a Quest needs no
# certificate step. The address changes on every start; the server answers only that origin and only with the access code.
#
#   scripts/ask_twin_public.sh            start, print the links, Ctrl+C stops the tunnel and the server
#   scripts/ask_twin_public.sh --idle-minutes 0      a field session: do not stop after two hours without a question
#   PORT=8765 PYTHON=/path/to/python scripts/ask_twin_public.sh --per-day 100     extra arguments go to ask_twin_server.py
#
# Needs: cloudflared (brew install cloudflared), the server's Python environment, ~/.config/ask-twin/env.
# No laptop speech (--no-tts): the Mac stays silent; a headset speaks with its own browser voice.
set -eu
ROOT=$(cd "$(dirname "$0")/.." && pwd)
PORT=${PORT:-8765}
PYTHON=${PYTHON:-$HOME/.venvs/ask-twin/bin/python}
LOG=$(mktemp -t ask-twin-tunnel)
command -v cloudflared >/dev/null || { echo "cloudflared not found: brew install cloudflared" >&2; exit 1; }

cloudflared tunnel --no-autoupdate --url "http://127.0.0.1:$PORT" >"$LOG" 2>&1 &
TUNNEL=$!
trap 'kill $TUNNEL 2>/dev/null || true' EXIT INT TERM
URL=
for _ in $(seq 1 30); do
  URL=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' "$LOG" | head -1 || true)
  [ -n "$URL" ] && break
  sleep 1
done
[ -n "$URL" ] || { echo "no tunnel address after 30 s; see $LOG" >&2; exit 1; }

CODE=$(LC_ALL=C tr -dc 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789' </dev/urandom | head -c 6)
# Announce the address (never the code) on the 'ask-endpoint' branch of the public repository, so a headset connects by typing
# only the code (twin/xr-ask.js ENDPOINT). One small file, written with git plumbing: the working tree and the current branch are
# not touched. ASK_PUBLISH=0 skips it; a failure only means the long address has to be typed.
announce() {
  [ "${ASK_PUBLISH:-1}" = 1 ] || return 0
  (cd "$ROOT" && git fetch -q origin ask-endpoint 2>/dev/null; parent=$(git rev-parse -q --verify FETCH_HEAD 2>/dev/null || true)
   git ls-remote --exit-code --heads origin ask-endpoint >/dev/null 2>&1 || parent=
   blob=$(printf '{"server":"%s","updated":"%s"}\n' "$1" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" | git hash-object -w --stdin) &&
   tree=$(printf '100644 blob %s\task-endpoint.json\n' "$blob" | git mktree) &&
   commit=$(git commit-tree "$tree" ${parent:+-p "$parent"} -m "Ask the twin: current temporary address") &&
   git push -q origin "$commit:refs/heads/ask-endpoint") >/dev/null 2>&1 &&
   echo "[ask-twin public] Address announced: on the headset open  ${SITE#https://}/vr/  (or /mr/) and type only the code  $CODE" ||
   echo "[ask-twin public] Could not announce the address (no push access or offline): type the short address below instead."
}
SITE=${SITE:-https://doe2park.github.io/Graduate-Project}
echo "[ask-twin public] address: $URL   (new on every start; it can take a minute before it opens)"
announce "$URL"
echo "[ask-twin public] Headset, fast: the page and the models come from the public site, only the AI calls come here."
echo "[ask-twin public] VR:  $SITE/vr/?ask=1&server=$URL&code=$CODE"
echo "[ask-twin public] MR:  $SITE/mr/?ask=1&server=$URL&code=$CODE"
echo "[ask-twin public] Short to type on the headset (hands over to the links above):"
echo "[ask-twin public]   ${URL#https://}/vr/?code=$CODE      ${URL#https://}/mr/?code=$CODE"
echo "[ask-twin public] PC on this laptop:  http://127.0.0.1:$PORT/scan-compare.html?view=overlay&style=lens&capture=2026-05-06&ask=1&code=$CODE"
echo "[ask-twin public] Everything through this address (slow: about 95 MB of models pass through the laptop; use it for local edits not yet on the site):"
echo "[ask-twin public]   $URL/vr/?direct=1&ask=1&code=$CODE   $URL/mr/?direct=1&ask=1&code=$CODE   $URL/scan-compare.html?view=overlay&style=lens&capture=2026-05-06&ask=1&code=$CODE"
cd "$ROOT"
"$PYTHON" scripts/ask_twin_server.py --no-tts --port "$PORT" --code "$CODE" --public-origin "$URL" "$@"
