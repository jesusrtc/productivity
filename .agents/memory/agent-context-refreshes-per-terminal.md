# Agent context refreshes per terminal

The user requires agents to check for changed Lab context on every turn, rather
than retain stale launch instructions. Use `lab context version` for a decimal
content fingerprint and `lab context update` for a silent unchanged check or the
fresh overview when it changes. Compare versions by equality, not ordering.

The launcher records the supplied version in the calling tmux session’s
`@lab_context_version`. Updates acknowledge only after successful output. Resolve
the exact TMUX socket and TMUX_PANE, including old sockets, and never target the
browser-selected terminal. No workspace instruction files are generated or edited.
Existing agents must read the new checker rule once; they cannot discover a rule
that only changed on disk. Ordinary context reads do not consume a pending update.

The October 15 user reproduction proved that a new Codex agent received the
status instructions but skipped reporting during a short sleep request. Context
now identifies the calling terminal and requires executed context/status commands
for every turn, including short tasks. Fixture tests of commands and UI alone do
not prove model compliance; distinguish native tests from actual provider checks.
