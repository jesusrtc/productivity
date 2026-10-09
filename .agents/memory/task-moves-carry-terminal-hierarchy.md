# Task moves carry terminal hierarchy

The user requested on October 9, 2026 that drag-and-drop task promotion and
nesting affect both tasks and terminals. Objective task branches now support
recursive children (up to 32 nested levels). Keep task/subtab/resource/session
IDs, task content, attachments, cwd and running processes when moving branches.
Reject cycles, invalid anchors, conflicting recurrence and stale revisions.

Task-row drops offer nesting or sibling placement; dropping on Tasks promotes
the branch to the root. Moving an owned primary terminal also moves its task.
Unowned extra terminals retain manual nesting. Reconcile saved browser terminal
parents, roots, ordering overrides and display merges after task ancestry or
order changes, while preserving extras and unrelated manual layouts. Polling
and reload must observe the persisted task hierarchy.
