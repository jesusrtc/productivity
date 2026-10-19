# Task moves carry terminal hierarchy

The user requested on October 9, 2026 that drag-and-drop task promotion and
nesting affect both tasks and terminals. Objective task branches now support
recursive children (up to 32 nested levels). Keep task/subtab/resource/session
IDs, task content, attachments, cwd and running processes when moving branches.
Reject cycles, invalid anchors, conflicting recurrence and stale revisions.

Task-row drops reorder above/below; Alt-drag offers nesting placement. Dropping
a task on Tasks promotes its branch to the root. Terminal drags never move tasks
and stay within their own task block; see
[the updated block rule](terminal-task-blocks-control-tab-dragging.md).
Unowned extra terminals retain manual nesting. Reconcile saved browser terminal
parents, roots and display merges after task ancestry changes, while preserving
internal task-tab order, extras and unrelated manual layouts. Task reordering
changes block order without clearing internal preferences. Polling
and reload must observe the persisted task hierarchy.
