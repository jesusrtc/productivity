# Selected tasks always have a visible terminal

The October 6, 2026 follow-up keeps In progress task terminals visible and adds the selected Objective task/subtask regardless of status. Include extra child terminals with that task's inherited context. When task focus ends or changes, non-WIP terminals for the previous task return to the filtered state. Settings can still reveal all terminals; sessions stay alive and task status is unchanged.

A deliberate task/subtask click in the sidebar opens its Markdown and selects its primary terminal. If no live primary exists, automatically create and associate a tmux terminal through the existing launch path. Reuse existing primary sessions and deduplicate repeated clicks. Passive terminal navigation, draft restoration, polling and task creation alone do not spawn terminals. Late creation saves its original association but does not attach over a different task or Objective selected meanwhile.

This supersedes the missing-terminal behavior in `task-clicks-activate-linked-terminal.md`, the prohibition on spawning from a clicked task in `terminal-tree-mirrors-tasks-and-inherits-context.md`, and the strict WIP-only visibility rule in `objective-terminals-default-to-wip-tasks.md`.
