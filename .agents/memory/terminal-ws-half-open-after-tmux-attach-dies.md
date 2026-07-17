---
name: terminal-ws-half-open-after-tmux-attach-dies
description: Server keeps the terminal WS open after its `tmux attach` child dies; clients only find out on next keystroke or via the 8s session poll
metadata:
  type: project
---

When the server-side `tmux attach` PTY child exits (session killed, client
detached), the WS handler in `core/src/core/routes/term.py` does NOT close the
WebSocket: `pump_pty_to_ws` just returns on EOF and the `receive_text()` loop
keeps waiting. The browser still shows "attached" on a frozen pane until either
(a) the user types (PTY write fails → server breaks → WS closes) or (b) the
frontend's 8s periodic session refresh notices the session vanished.

**Why:** verified live 2026-07-09 while building terminal auto-reconnect —
`tmux detach-client`/`kill-session` produced no WS close for 30s+.

**How to apply:** the frontend auto-reconnect (endless capped backoff +
`_termSessionGone` auto-restore in `lab-app.js`) deliberately leans on the 8s
poll to catch confirmed-gone sessions, so worst-case detection is ~8s. If that
lag ever matters, the server fix is to close the WS when the pump hits EOF.
Related: [[terminal-latency-invariants]]. Testing gotcha: Playwright's
`context.setOffline(true)` does not kill established WebSockets — only new
dials/fetches fail.
