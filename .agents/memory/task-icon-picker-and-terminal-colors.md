# Task icon picker and terminal colors

On October 9, 2026 the user requested a picker on the task's left badge and icon
area. Show distinct asset icons first, include all built-in service icons (GitHub
must be available even without a matching asset), then suggested emojis and a
custom emoji field. Include the same worktree color selector to customize task
terminal text. Preview both settings and save together; provide default resets.

Keep task status separate and its secondary-click menu available. Icon selection
alone does not attach or create an asset. The saved choice and text color reach
the task's primary, inherited, merged and recommended terminals. Preserve each
worktree's own color. CLI task-update supports icon and terminal_color; legacy
asset icon choices and explicit icon drops still work.

This expands the drop-only rule in
[Task status and terminal icons are separate](task-status-and-terminal-icons-are-separate.md).
