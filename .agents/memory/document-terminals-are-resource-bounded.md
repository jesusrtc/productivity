# Document terminals preserve conversations and release idle processes

The client wants a terminal ready on opening each task/document, with the exact
previous conversation, without runaway resource use. They rejected a hard cap
of three running document terminals. Opening never sends an agent task.

Keep one idle agent process ready by default; hidden idle processes sleep after
five minutes or sooner when another document needs the idle slot. The legacy
settings key maxRunning now controls the idle cache only, not active work.
Attached terminals, unsent input, active turns, approval waits and unknown work
stay protected. Low OS memory headroom delays new starts with a visible waiting
state and automatic retry; reserve additional headroom for recent launches.

Save exact provider conversation IDs before sleeping. These small bookmarks
never expire once a conversation exists. The 36-hour expiry applies only to
unused bookmarks, not saved conversations. All content tabs share the root
identity. Keep one visible xterm/WS and dispose it on close/switch/hidden-page
transitions; ordinary terminals are untouched.

Use list-panes -s with an exact session target for identity checks. tmux
display-message may return success and empty fields for a missing session;
treating this as unknown activity caused phantom running entries and blocked
new terminals. Reconcile missing/exited sessions on status and opening too.

Input callbacks only update RAM; ignore terminal protocol/mouse replies when
tracking unsent text. Cleanup runs at low frequency. Inspect OS memory only
during startup/cleanup, never on the terminal byte path. See
docs/document-terminals.md for settings and compatibility.

Both primary and secondary terminal device-attribute replies (CSI ?…c and
CSI >…c) must be ignored as input. Real xterm attach sends both; treating the
secondary reply as typed text produced a false unsent-draft flag on every open.
