# Objective demo uses asset buckets

The user requested the asset bucket redesign in the browser-only Home demo
first, after updating its appearance to the production UI. Its sidebar order
is Unassigned, Objective pinned/shared assets, Tasks, then the selected task's
assets. Archive is collapsed below; sources remain recoverable. Each task or
subtask owns its asset references. Dragging any asset onto a task attaches it;
shared pins remain common across tasks. Task console drags include shared
references plus mandatory details and task-specific references, deduplicated
and excluding Archive. Terminal-name drops associate the task without pasting.
Do not apply these experimental buckets to live workspace registries without
further user authorization.
