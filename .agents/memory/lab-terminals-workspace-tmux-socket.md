# Lab terminals: default tmux socket + stripped $TMUX (updated 2026-07-01)

Decision changed: Lab terminals run on the **default** tmux socket, with session
names carrying the namespace instead: `neurona-<workspace>-<project>-<tab>-<hash6>`
(workspace = registry id from `~/.lab/workspaces.toml`, e.g. `ssd`/`local`).
Do not reintroduce per-workspace `-L`/`-S` sockets — split sockets were the root
cause of "opening a project creates a new session instead of attaching": sessions
created while the server ran inside tmux landed on the containing server's socket
(inherited `$TMUX`) and became invisible to launchd-run instances.

The invariant that keeps this safe: **every tmux subprocess call in term.py runs
with `TMUX`/`TMUX_PANE` stripped from the child env** (`_tmux_child_env()`), so
all session operations hit the default server no matter where the lab server was
launched. Regression-tested in test_term_routes.py.

The earlier hazard this note used to warn about (default server first started
from a sandboxed Codex command → panes inherit a broken env) is still real; if
panes start failing shell startup with cwd/readability errors, kill the default
tmux server and let it restart from a clean environment rather than moving Lab
back onto a custom socket. `attach_command` for every session is exposed by the
sessions API.
