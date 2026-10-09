# Pending task actions and deadlines

The user wants the workspace Objective sidebar and Tasks dashboard to show all
unfinished tasks, subtasks and unchecked action items, without requiring WIP,
hover or task selection. Completed and discarded tasks are hidden by default.
This supersedes the sidebar's former single-parent expansion rule; task clicks
keep all pending branches visible and preserve the assets section's position
until the pending row count changes.

Action items can start with `[YYYY-MM-DD HH:mm]` after the checkbox. Treat that
as a local deadline, retain the original Markdown and expose overdue/near-due
work. Clicking an action opens its exact source document/tab, reveals folds,
scrolls and highlights that occurrence; Edit selects its source line.

Repeating branches stay hidden until their configured show-again/reactivation
time, including in completed-task history. Then the same task IDs return with
the existing task/subtask/action checkboxes reset.
