# Terminal automations belong to the workspace

Save named command groups in Settings → workspace → Terminal automations, with
an additional shortcut under Terminal sessions. Definitions are server-owned
in the workspace’s .lab/terminal-automations.json, shared across browsers; save
through the validated API with revision checks. Saving never runs commands.

Secondary-click any workspace terminal, including a fixed main, then Launch
automation… to select a group and preview commands and resolved paths. Empty
paths inherit the parent’s fixed launch cwd, relative paths resolve against it,
and absolute or ~/ paths are supported. Validate every directory first. Start
commands in order in separate plain tmux child tabs without waiting for earlier
commands to exit; dependent steps can be combined in one shell command.

Commands execute once at creation through a quoted shell argument, not terminal
input. Print the exit code and retain a usable shell and logs. Do not persist an
auto-run command in saved session metadata or replay it on ordinary restore.
A repeated request with the same run UUID adopts existing children; later
explicit launches use another UUID. Partial failures retain started children.

Capture the workspace, parent identity and Objective/task selection before any
await. Persist child layout to that original browser scope even after navigation,
save Objective or workflow context without claiming a main or primary task, and
only select the first child if the original selection is still current. Main
terminals stay roots and fixed in position but can host automation children.
Workflow main children stay visible; Objective main children follow the active
Objective; task children inherit WIP/selected-task visibility and context.
