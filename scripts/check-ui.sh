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

# Start the server only when the resolved URL doesn't answer. Probing the
# URL (not pgrep, not the pidfile) is the only detection that works for
# every supervision mode: the launch agent runs a resolved Python whose
# command line doesn't contain "core/.venv/bin/python", so process-name
# matching misclassifies it as stopped and double-starts on the default
# port (see .agents/memory/check-ui-launch-agent-process-detection.md).
STARTED_BY_US=""
_lab_alive() {
  curl -sS -m 3 -o /dev/null -w '%{http_code}' \
    "$("$REPO_ROOT/scripts/lab-url.sh")/" 2>/dev/null | grep -Eq '^[23][0-9][0-9]$'
}
if ! _lab_alive; then
  make start-bg >/dev/null
  STARTED_BY_US=1
  # Give uvicorn a moment to finish lifespan startup. Re-resolve the URL
  # because the server only writes the workspace-local port file once it's listening.
  for _ in 1 2 3 4 5; do
    if _lab_alive; then
      break
    fi
    sleep 0.5
  done
  # The port may differ from the pre-start resolution; recompute the target
  # URL unless the caller passed an explicit override.
  if [[ -z "${1:-}" ]]; then
    LAB_URL="$("$REPO_ROOT/scripts/lab-url.sh")"
    URL="$LAB_URL/?ui_check=1"
  fi
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

# Mint a short-lived-enough local admin session without putting a plaintext
# password in this script. The application still validates the signed cookie
# exactly as it does for an interactive browser.
if [[ "${UI_UNAUTHENTICATED:-}" == "1" ]]; then
  LAB_UI_AUTH_COOKIE=""
else
  LAB_UI_AUTH_COOKIE="$(core/.venv/bin/python -c 'import sys; from core import auth; user = auth.get_user(sys.argv[1]); assert user is not None; print(auth.issue_session(user))' "${UI_CHECK_USER:-admin}")"
fi
export LAB_UI_AUTH_COOKIE

# Start Chrome on a fresh profile, then use its DevTools socket to install the
# HttpOnly session cookie before navigating. --dump-dom cannot set cookies,
# so without this step it would only validate the login page.
"$CHROME" \
  --headless \
  --disable-gpu \
  --no-sandbox \
  --no-first-run \
  --no-default-browser-check \
  --user-data-dir="$UDD" \
  --remote-debugging-port=0 \
  --hide-scrollbars \
  about:blank >/dev/null 2>&1 &
CHROME_PID=$!

# Wait for Chrome to publish its ephemeral DevTools port.
deadline=$(( $(date +%s) + CHROME_TIMEOUT ))
while [[ $(date +%s) -lt $deadline ]]; do
  if [[ -s "$UDD/DevToolsActivePort" ]]; then
    break
  fi
  sleep 0.2
done

if [[ ! -s "$UDD/DevToolsActivePort" ]]; then
  echo "UI CHECK FAILED — Chrome did not open its DevTools port" >&2
  exit 1
fi

node "$REPO_ROOT/scripts/chrome-dump-auth.mjs" "$UDD" "$URL" "$DOM_DUMP" "${UI_SCREENSHOT:-}"

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
  MIN_BODY_SIZE="${UI_MIN_BODY_SIZE:-2048}"
  if [[ "$BODY_SIZE" -lt "$MIN_BODY_SIZE" ]]; then
    echo "UI CHECK WARN — DOM is suspiciously small ($BODY_SIZE bytes); page may not have rendered"
    STATUS=1
  else
    echo "UI CHECK PASSED ($URL)"
  fi
fi

exit $STATUS
