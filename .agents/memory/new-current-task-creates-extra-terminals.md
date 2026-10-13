# New terminals belong directly to their selected context

A task can have multiple independent terminals, with one primary for task
navigation. Explicit **+ New → Terminal / agent → Current task** creates and
selects a fresh session of the requested type, with its own persisted task
association. Current Objective/workflow likewise save their own context.

The user rejected automatically nesting a new terminal beneath the active or
primary terminal. Do not derive new task membership from browser parent links.
The Objective `terminal` action accepts `primary: false` with `task_id` to add a
member without replacing the primary; its first member becomes primary. Normal
task navigation prefers the primary. Promoting an independent member changes
only the primary role, preserves every member's task association and leaves
terminal nesting unchanged. The chosen launch folder stays fixed.

Explicit **New subterminal**, automation groups and deliberate nesting retain
their existing child behavior. This supersedes the inherited-nesting approach
from the initial Current task fix and the one-direct-task-terminal restriction
in terminal-tree-mirrors-tasks-and-inherits-context.md.
