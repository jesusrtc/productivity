# Worktrees browse mode restores task assets

Worktrees sits above Tasks, starts folded, and reveals on hover (or keyboard focus). Track Root and the Objective folder in gray plus every Objective-associated checkout. A selected worktree keeps the browser open until the Worktrees header is folded or another task/Objective is opened, so moving to the center does not interrupt assignment.

Selecting a worktree replaces left-side task/assets buckets with that checkout's native Recently updated and Files; the center shows every task and subtask unfolded for drag/drop. Repeated worktree drops add membership to multiple tasks through existing folder asset references. Preserve each task's Markdown, canonical title, icon, context and other assets. Display assigned worktree names and colors in the task label, combining names when multiple scopes are assigned.

Folding restores the task selected before browsing (or the first task assigned during browsing when no task was selected), its Markdown and assets. Task mode shows only recent files across its explicitly assigned, non-archived worktrees, including Root/Objective assignments; it hides the full Files tree. Each recent row retains its checkout owner for file actions. Active Objective directory and recent-file reads refresh at five seconds with stale-response guards; ordinary project cache defaults stay at one minute.

This supersedes the older Tasks-first ordering and worktree-click empty Files center in `objective-tasks-and-fixed-gray-folders.md`, `worktrees-stay-visible-and-group-by-task.md`, and `worktree-clicks-show-native-files.md`.
