# Worktrees inherit their project color

Worktree swatches, sidebar rails, and linked terminal colors inherit the parent
project color by default, including subsequent project color edits. Persist
only explicit per-worktree overrides; scanning or saving settings must not
freeze an inherited color. Use project color clears an override. Legacy
unversioned gray entries were auto-seeded by scans and migrate to inheritance;
version 2 preserves explicitly selected gray like any other custom color.
