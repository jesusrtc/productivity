#!/usr/bin/env bash
# Print the lab server's URL (or just its port with --port).
#
# Source of truth precedence:
#   1. $LAB_PORT (env var, honored by the server itself)
#   2. $LAB_WORKSPACE/.lab/state/server.port (written by the server on startup)
#   3. active workspace in $LAB_HOME/workspaces.toml or ~/.lab/workspaces.toml
#   4. .lab-server.port (legacy)
#   5. 3333
#
# Examples:
#   $(scripts/lab-url.sh)              # http://localhost:3333
#   $(scripts/lab-url.sh)/api/nb/exec  # http://localhost:3333/api/nb/exec
#   $(scripts/lab-url.sh --port)       # 3333
#
# Any script, doc snippet, or Claude tool invocation that needs to talk to
# the lab server SHOULD route through this — that way switching ports via
# `make start PORT=4444` is enough; no other config needs to change.

set -e

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

port="${LAB_PORT:-}"
if [[ -z "$port" && -n "${LAB_WORKSPACE:-}" && -f "$LAB_WORKSPACE/.lab/state/server.port" ]]; then
  port="$(tr -d '[:space:]' < "$LAB_WORKSPACE/.lab/state/server.port")"
fi
if [[ -z "$port" ]]; then
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
port="${port:-3333}"

if [[ "${1:-}" == "--port" ]]; then
  echo "$port"
else
  echo "http://localhost:$port"
fi
