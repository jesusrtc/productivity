# Lab terminals use bounded rolling tmux sockets

Lab's global terminal routing state lives at `$LAB_HOME/tmux-sockets.json`.
The implicit/default state has no file and preserves the exact historical
`tmux ...` command shape. `lab terminal rotate`, run directly from a working
non-tmux iTerm, seeds a named tmux server so it captures that macOS security
context.

Routing is strictly bounded to one active and at most one draining generation.
New terminals and server control sessions use active; existing sessions retain
`tmux_socket` affinity in runtime metadata. Empty drains are pruned during
normal listing/status calls, with no background thread or keeper session.
Named active servers use `exit-empty off`; named draining servers return to
`exit-empty on`. Never silently recreate a dead named active socket from the
backend context—ask the user to rotate again from iTerm.

Socket discovery belongs only in lifecycle/attach paths. Do not add it to the
PTY/WebSocket byte loop: typing, output, scrolling, and resizing must remain
direct and allocation-free apart from their existing queues.
