# Task blocks control terminal tab dragging

The user clarified on October 19, 2026: task/subtask DFS order determines invisible
contiguous terminal blocks. Include direct members, inherited children and
automation terminals. Derive block order from canonical tasks each render.

Only task title drags move whole branches and blocks. Individual tab drags stay
inside their own task block, without moving descendants or changing task/parent
context. Task-bound rows render individually; real parent links still supply
context, appearance, recovery and primary selection. Generic terminal hierarchy
and fixed workspace/Objective mains retain their behavior. Explicit child or
automation creation still establishes inheritance.

Saved tab order within a task survives task moves/reparenting and browser reload.
Ignore stale cross-block ordering anchors. Same IDs in different Objectives are
different blocks. Preserve running sessions, cwd, conversations, status and assets.
This supersedes primary-terminal-drag-moves-task behavior and task-bound hover
nesting from the older terminal/task hierarchy notes.
