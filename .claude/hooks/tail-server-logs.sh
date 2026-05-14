#!/usr/bin/env bash
# Tail the four split server log files into Claude's UserPromptSubmit context
# so every turn starts with fresh visibility into recent backend/frontend
# errors. Discards stdin (the hook payload — we don't need it). Output is
# intentionally short: errors get 30 lines, the noisier info files get 10.

LOG_DIR="/Users/jcortes/src/productivity/logs"

emit() {
  local name="$1" limit="$2" path="${LOG_DIR}/$1.log"
  echo "=== ${name}.log (last ${limit}) ==="
  if [ -s "$path" ]; then
    tail -n "$limit" "$path"
  else
    echo "(empty or missing)"
  fi
}

{
  echo "── server log tails @ $(date -u +%FT%TZ) ──"
  emit backend-errors  30
  emit backend-info    10
  emit frontend-errors 30
  emit frontend-info   10
}
exit 0
