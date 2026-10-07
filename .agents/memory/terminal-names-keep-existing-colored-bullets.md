# Terminal names keep existing colored bullets

The user clarified on October 6, 2026: if a terminal name already contains a
colored bullet (for example a red or blue worktree name), keep that existing
bullet and color; do not add a second task-status dot. Apply this to primary,
recommended and inherited-context terminal rows. A task with exactly one worktree keeps that
worktree's bullet. Tasks with multiple assigned worktrees now keep their own
name and a small status dot; see task-name-overrides-need-one-worktree.md. In the compact rail hide
the name text while keeping its existing colored bullets visible.

Use the small task-status dot only when the name has no worktree bullet. Keep
status information in accessible labels and hover text even when its separate
dot is omitted. This refines terminal-task-statuses-use-small-dots.md.
