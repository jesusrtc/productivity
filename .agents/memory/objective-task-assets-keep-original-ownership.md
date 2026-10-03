# Objective task assets keep original ownership

The user wants worktrees, folders, files, documents, internal document subtabs,
notebooks, links and sublinks attachable to individual tasks by drag and drop.
Task rows, the focused task control and the asset dialog accept drops. Store
stable resource/child references or normalized folder targets; importing a file
or Assistant document links it without copying its content. Preserve existing
resource scope and original Assistant ownership. Repeated drops deduplicate.

Required task details are implicit and cannot be detached. Optional assets can
be detached without deleting content. The task's chosen icon comes from one of
its assets; detaching/unlinking that asset resets the icon to details. Terminal
associations use task_id and reopen that task's details in Focus mode; neither
direction of terminal/task association sends terminal input.
