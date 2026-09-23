# Terminal indicators persist until finish or review

The user corrected the terminal indicator rules on 2026-09-22. Yellow stays
through unknown/partial reads, missing live IDs, waiting for input, disconnection,
navigation, and reloads until a verified finish/interruption/error. Long Codex
runs can push task_started out of the 2 MiB transcript tail; recognize ongoing
main-agent reasoning and tool calls too, and retain verified browser state.

Unread green disappears only after the full continuous viewing interval
(20 seconds by default) or a real double-click on the tab. Single clicks and
two separate clicks never acknowledge it. New work cannot hide or acknowledge
green: display yellow and green side by side, and reset/pause the viewing timer
while work remains in progress. Double-click with nothing unread still renames;
the context menu also offers Rename. Preserve shared-view acknowledgements.

This supersedes the clearing/priority rules in terminal-working-steady-yellow-dot.md
and terminal-completion-blinking-dot.md, and the separate-click shortcut in
terminal-completion-second-click.md. See docs/terminal-completion.md.
