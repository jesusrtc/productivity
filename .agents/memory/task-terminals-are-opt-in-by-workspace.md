# Task terminals are opt-in by workspace

Settings → workspace → Terminal sessions offers “Each task gets its own
terminal,” off by default. Persist `task_terminals` in that workspace's
`.lab/objectives-state.json` via the Objective `terminal-policy` action, scoped
by vault/workspace and guarded by revision. It applies to every Objective in
that workspace and every browser. Do not repurpose workspace/task metadata.

Off means no recommended task placeholders and no new terminal from ordinary
task selection. Task details still open; existing linked terminals can be
activated and remain available under their usual filters. Explicit + New →
Current task still creates/reuses a task terminal. On restores recommended
task placeholders and creation/reuse when deliberately selecting a task.
Changing the setting never closes or reassigns existing sessions. This updates
the earlier always-on behavior in `selected-task-always-has-visible-terminal.md`.
