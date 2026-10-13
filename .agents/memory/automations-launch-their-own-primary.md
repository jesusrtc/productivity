# Automations launch their own primary

Use + New → Launch automation… to create the automation’s own terminals for the
active task. The first terminal in the saved definition is the task’s primary;
subsequent steps nest beneath it, in definition order. No starter shell or manual
primary selection is needed. Replacing a primary leaves the old session running.

Capture workspace, Objective, task and folder when opening the launcher, preview
all commands and directories, and label the first step Primary. Persist ownership
in the launch API so CLI requests and partial failures retain the same primary.
Parentless requests accept objective_id, task_id and optional cwd. The first
terminal stays visible when it owns an In progress task; automation naming alone
does not make it a child. Browser nesting still belongs to the launching view.

Secondary-click Launch automation… on an existing terminal remains the child
launch mode; all steps inherit that existing parent. The new mode extends the
older terminal-automations-belong-to-the-workspace rule about never taking task
ownership. Saving, previews, reconnects and ordinary restore never replay commands.
