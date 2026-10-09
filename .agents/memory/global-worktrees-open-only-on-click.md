# Global Worktrees opens only on click

The top sidebar Worktrees group starts folded and opens only through explicit
activation of its header. Hover and focus do not open it. Pointer departure
does not close it; clicking anywhere outside the group folds it immediately.
Outside dismissal keeps the selected checkout, Files and assignment view;
explicitly folding the open header restores the prior task as before. Opening
a checkout through the task's Worktrees section or a linked terminal must not
automatically expand the global group.

Dismiss on click rather than pointerdown so folding cannot move a native click
or drag target between mouse press and release. Update the disclosure in place
to preserve the clicked node for its existing handler.

This supersedes hover/focus expansion and browse-pinned visibility in
`worktree-browse-restores-task-assets.md`.
