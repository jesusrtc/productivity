# CLI task navigation shares terminal policy

Named `lab ui command task-open` must use normal task-click activation, including
the workspace task-terminal setting and In progress filter. A paused task opens
details without activating or creating its filtered terminal. Task and Objective
navigation must refresh data to see preceding `lab api` mutations, rather than
relying on the browser's short-lived Objective cache.

Keep the combined CLI → HTTP → browser regression covering API status changes,
task clicks, link-modal editing, asset assignment and terminal renaming; tests
of each feature alone did not catch these navigation differences.
