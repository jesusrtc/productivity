# Task agent drops include all asset references

The user explicitly wants passing a task to an agent to include the task and
every attached asset reference. Dragging an individual task title or focused
task control inside a console carries one ordered reference bundle: task
details with its stable subtab ID, then all attached paths/URLs. Keep exact
document subtabs and link children, plus file, folder and worktree source paths.
Use the shared scoped-prompt formatter described in
[Task agent drops use scoped prompts](task-agent-drops-use-scoped-prompts.md),
preserving typed Context / This task sections without submitting Enter. Block an unavailable bundle rather than
silently dropping a missing source. Dropping onto a terminal name associates
the task instead of pasting the bundle.
