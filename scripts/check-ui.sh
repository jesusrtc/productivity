#!/usr/bin/env bash
# UI smoke check: render the unified server's home view in headless Chrome,
# grep the DOM for JS errors captured by the inline error banner, and exit
# non-zero if any are found.
#
# Usage: make check-ui     (from monorepo root)
#        scripts/check-ui.sh [url]
#
# Also accepts a URL override — useful for testing a specific project view:
#   scripts/check-ui.sh "$(scripts/lab-url.sh)/?project=/abs/path"

set -e

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

LAB_URL="$("$REPO_ROOT/scripts/lab-url.sh")"
BASE_URL="${1:-$LAB_URL/}"
# Append ?ui_check=1 so the page disables persistent timers + WebSocket.
# Without that, Chrome's --dump-dom never reaches network idle.
if [[ "$BASE_URL" == *"?"* ]]; then
  URL="${BASE_URL}&ui_check=1"
else
  URL="${BASE_URL}?ui_check=1"
fi
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PID_FILE=".lab-server.pid"

if [[ ! -x "$CHROME" ]]; then
  echo "ERROR: Google Chrome not found at $CHROME" >&2
  exit 2
fi

# Start the server if it isn't running. Use pgrep (not the pidfile — which
# can lie if the user started from another shell or after a crash).
STARTED_BY_US=""
if ! pgrep -f "core/.venv/bin/python -m core" >/dev/null 2>&1; then
  make start-bg >/dev/null
  STARTED_BY_US=1
  # Give uvicorn a moment to finish lifespan startup. Re-resolve the URL
  # because the server only writes .lab-server.port once it's listening.
  for _ in 1 2 3 4 5; do
    PING_URL="$("$REPO_ROOT/scripts/lab-url.sh")/api/ping"
    if curl -sS -o /dev/null -w '%{http_code}\n' "$PING_URL" 2>/dev/null | grep -q '^200$'; then
      break
    fi
    sleep 0.5
  done
fi

cleanup() {
  # Kill the Chrome we spawned + any helper processes using our temp UDD.
  # The main Chrome process forks helpers that don't die from `kill $CHROME_PID`.
  if [[ -n "${UDD:-}" ]]; then
    pkill -9 -f "user-data-dir=${UDD}" 2>/dev/null || true
  fi
  if [[ -n "$STARTED_BY_US" ]]; then
    # `make stop` now reliably kills the server by exact command-line match,
    # not the flaky pidfile — so this is enough.
    make stop >/dev/null 2>&1 || true
  fi
  [[ -n "${UDD:-}" ]] && rm -rf "$UDD" || true
  [[ -n "${DOM_DUMP:-}" ]] && rm -f "$DOM_DUMP" || true
}
trap cleanup EXIT

# Fresh user-data-dir per run keeps Chrome from clobbering an interactive session.
UDD="$(mktemp -d -t lab-ui-check)"
DOM_DUMP="$(mktemp -t lab-ui-dom)"

CHROME_TIMEOUT="${CHROME_TIMEOUT:-10}"

# macOS doesn't ship `timeout`. Run Chrome in the background, poll the dump
# file for content (it's written the moment --dump-dom fires), and kill
# Chrome as soon as we have the DOM — Chrome sometimes doesn't self-exit on
# headless mode even after dumping.
"$CHROME" \
  --headless \
  --disable-gpu \
  --no-sandbox \
  --no-first-run \
  --no-default-browser-check \
  --user-data-dir="$UDD" \
  --virtual-time-budget=4000 \
  --hide-scrollbars \
  --dump-dom \
  "$URL" > "$DOM_DUMP" 2>/dev/null &
CHROME_PID=$!

# Wait up to CHROME_TIMEOUT seconds for the dump file to reach a minimum size
# (Chrome writes the full DOM in one go; 2KB rules out "just headers").
deadline=$(( $(date +%s) + CHROME_TIMEOUT ))
while [[ $(date +%s) -lt $deadline ]]; do
  if [[ -s "$DOM_DUMP" ]] && [[ $(wc -c < "$DOM_DUMP") -gt 2048 ]]; then
    # DOM was flushed. Give Chrome ~300ms more to finish any trailing bytes.
    sleep 0.3
    break
  fi
  sleep 0.2
done

kill "$CHROME_PID" 2>/dev/null || true
wait "$CHROME_PID" 2>/dev/null || true
# Kill any remaining helper processes from this run (they share the UDD).
pkill -9 -f "user-data-dir=$UDD" 2>/dev/null || true

STATUS=0
ERRORS="$(python3 - "$DOM_DUMP" <<'PY'
import re, sys
html = open(sys.argv[1], encoding='utf-8', errors='replace').read()
m = re.search(r'id="__js_errors__"[^>]*data-errors="([^"]*)"', html)
if not m:
    # Error banner element missing entirely — means the page didn't render
    # past the head. That's itself a failure.
    print("(no error banner in DOM — page may have failed to render)")
    sys.exit(0)
errs = m.group(1).replace('&quot;', '"').replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>').strip()
if errs:
    print(errs)
PY
)"

if [[ -n "$ERRORS" ]]; then
  echo "UI CHECK FAILED — JS errors captured at $URL:"
  echo "$ERRORS" | sed 's/^/  /'
  STATUS=1
else
  # Sanity: page has a body and content (not just "<html></html>").
  # Banner presence already told us JS ran far enough to bind listeners.
  BODY_SIZE=$(wc -c < "$DOM_DUMP")
  if [[ "$BODY_SIZE" -lt 2048 ]]; then
    echo "UI CHECK WARN — DOM is suspiciously small ($BODY_SIZE bytes); page may not have rendered"
    STATUS=1
  else
    echo "UI CHECK PASSED ($URL)"
  fi
fi

exit $STATUS
