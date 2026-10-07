# Task name overrides need one worktree

The user clarified on October 7, 2026: use an assigned worktree's name and color
as a task label only when exactly one non-archived scope is assigned. With zero
or multiple worktrees, preserve the task's own title in the sidebar, center,
task header, current tab and primary/recommended terminal label. Keep canonical
Markdown, task identity, icons, context and all memberships untouched.

The task union still reads recent files across every assigned worktree. A
multi-worktree task terminal has no worktree bullet in its task name, so use the
existing small task-status dot; one worktree retains its colored bullet without
an extra dot. This supersedes concatenating worktree names in
worktree-browse-restores-task-assets.md and the multiple-name case in
terminal-names-keep-existing-colored-bullets.md.
