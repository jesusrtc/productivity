---
name: framework-update-restarts-in-place
description: The admin top-bar update control must pull origin/main serially, exec-restart the current server process, and verify a new boot before reloading
type: feedback
---

The admin-only update button beside Settings runs `git pull --rebase --autostash
origin main` in the Lab framework checkout and only then restarts. The server
replaces itself with `python -m core` via `exec`, preserving its environment and
avoiding a second process racing for the same listening port. The browser polls
the authenticated runtime identity endpoint and reloads only after the boot ID
changes. A pull failure is shown without restarting.

For manual updates, pull and restart must also run serially; shell `&` backgrounds
the pull and creates a race. `make restart` falls back to its requested `PORT`
when the workspace port-state file is absent.
