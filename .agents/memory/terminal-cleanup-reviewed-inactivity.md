# Terminal cleanup uses reviewed inactivity snapshots

The Cleanup button sits next to Logs in Home, vaults, Assistant, and workspace
views. Its admin-only modal groups live tmux candidates across every registered
vault plus Assistant and the framework root. Only sessions inactive for strictly
more than seven days qualify. Last used is the maximum of creation, tmux activity,
last attachment, and Lab's recorded detach time. Connected sessions, managed
servers, known working/waiting agents, and managed document drafts are excluded.

Cleanup submits exact candidate fingerprints, never a workspace-wide kill. The
server rechecks freshness and tmux itself checks session ID, creation time, pane
PID, attachments, and activity immediately before killing the exact target.
Disable autospawn first, remove only confirmed saved tabs, and preserve provider
conversations. Home combines registries; prefer runtime ownership over recovery.

Tmux commands accepting a pane target (`if-shell -t`, `set-option -t`) need
`=session-name:` with a trailing colon for reliable exact targeting. A bare
`=session-name` can resolve an empty format context. `kill-session` uses the
session target `=session-name`. Verify destructive code using isolated tmux
sockets and fixtures, never the user's actual candidate sessions.
