#!/usr/bin/env bash
# Print the lab server's URL (or just its port with --port).
#
# Source of truth precedence:
#   1. $LAB_PORT (env var, honored by the server itself)
#   2. .lab-server.port (written by the server on startup)
#   3. 3333 (legacy default)
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
if [[ -z "$port" && -f "$REPO_ROOT/.lab-server.port" ]]; then
  port="$(tr -d '[:space:]' < "$REPO_ROOT/.lab-server.port")"
fi
port="${port:-3333}"

if [[ "${1:-}" == "--port" ]]; then
  echo "$port"
else
  echo "http://localhost:$port"
fi
