#!/usr/bin/env bash
# Print the lab server's URL, its live port with --port, or the client's
# persistent setting with --configured-port.
#
# Source of truth precedence:
#   1. $LAB_PORT (env var, honored by the server itself)
#   2. $LAB_WORKSPACE/.lab/state/server.port (written by the server on startup)
#   3. active workspace in $LAB_HOME/workspaces.toml or ~/.lab/workspaces.toml
#   4. checkout-local runtime state / .lab-server.port (legacy)
#   5. client checkout LAB_PORT in .env
#   6. active workspace [server].port in lab.toml
#   7. 3333
#
# Examples:
#   $(scripts/lab-url.sh)              # http://localhost:3333
#   $(scripts/lab-url.sh)/api/nb/exec  # http://localhost:3333/api/nb/exec
#   $(scripts/lab-url.sh --port)       # 3333
#   $(scripts/lab-url.sh --configured-port) # .env / workspace configured port
#
# Any script, doc snippet, or Claude tool invocation that needs to talk to
# the lab server SHOULD route through this so both the workspace setting and
# one-run `make start PORT=4444` overrides are discovered consistently.

set -e

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

active_workspace="$(
  LAB_HOME="${LAB_HOME:-$HOME/.lab}" python3 -c '
import os, tomllib
from pathlib import Path
registry = Path(os.environ["LAB_HOME"]).expanduser() / "workspaces.toml"
if registry.is_file():
    data = tomllib.loads(registry.read_text())
    active = data.get("active")
    for row in data.get("workspaces") or []:
        if str(row.get("id")) == str(active):
            print(Path(str(row.get("path", ""))).expanduser())
            break
' 2>/dev/null || true
)"
configured_workspace="${LAB_WORKSPACE:-$active_workspace}"
configured_port=""
if [[ -n "$configured_workspace" && -f "$configured_workspace/lab.toml" ]]; then
  configured_port="$(
    LAB_CONFIG_WORKSPACE="$configured_workspace" python3 -c '
import os, tomllib
from pathlib import Path
path = Path(os.environ["LAB_CONFIG_WORKSPACE"]).expanduser() / "lab.toml"
try:
    value = (tomllib.loads(path.read_text()).get("server") or {}).get("port")
except (OSError, tomllib.TOMLDecodeError, AttributeError):
    value = None
if isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 65535:
    print(value)
' 2>/dev/null || true
  )"
fi
client_env_file="${LAB_ENV_FILE:-$REPO_ROOT/.env}"
client_port=""
if [[ -f "$client_env_file" ]]; then
  client_port="$(
    LAB_CLIENT_ENV_FILE="$client_env_file" python3 -c '
import os
from pathlib import Path
path = Path(os.environ["LAB_CLIENT_ENV_FILE"]).expanduser()
try:
    lines = path.read_text().splitlines()
except OSError:
    lines = []
for raw in lines:
    line = raw.strip()
    if not line or line.startswith("#"):
        continue
    if line.startswith("export "):
        line = line[7:].lstrip()
    key, separator, value = line.partition("=")
    if separator != "=" or key.strip() != "LAB_PORT":
        continue
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in (chr(39), chr(34)):
        text = text[1:-1]
    try:
        port = int(text)
    except ValueError:
        break
    if 1 <= port <= 65535:
        print(port)
    break
' 2>/dev/null || true
  )"
fi
configured_port="${client_port:-${configured_port:-3333}}"

if [[ "${1:-}" == "--configured-port" ]]; then
  echo "$configured_port"
  exit 0
fi

port="${LAB_PORT:-}"
if [[ -z "$port" && -n "${LAB_WORKSPACE:-}" && -f "$LAB_WORKSPACE/.lab/state/server.port" ]]; then
  port="$(tr -d '[:space:]' < "$LAB_WORKSPACE/.lab/state/server.port")"
fi
if [[ -z "$port" ]]; then
  if [[ -n "$active_workspace" && -f "$active_workspace/.lab/state/server.port" ]]; then
    port="$(tr -d '[:space:]' < "$active_workspace/.lab/state/server.port")"
  fi
fi
if [[ -z "$port" && -f "$REPO_ROOT/.lab/state/server.port" ]]; then
  port="$(tr -d '[:space:]' < "$REPO_ROOT/.lab/state/server.port")"
fi
if [[ -z "$port" && -f "$REPO_ROOT/.lab-server.port" ]]; then
  port="$(tr -d '[:space:]' < "$REPO_ROOT/.lab-server.port")"
fi
port="${port:-$configured_port}"

if [[ "${1:-}" == "--port" ]]; then
  echo "$port"
else
  echo "http://localhost:$port"
fi
