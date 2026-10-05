# New terminals choose workflow, Objective or worktree

The user requires an explicit choice when opening a new terminal: current
workflow (the active workspace root), current Objective (its own directory),
or a specific worktree belonging to that Objective. The worktree category opens
a second list restricted to that Objective's registered checkouts/folders,
including those not pinned or currently shown in task assets. Do not mix in
another Objective's pinned folders. With no worktrees, disable that category
while retaining workflow and Objective launches.

Current Objective saves a whole-Objective terminal mapping so it sorts first
and reopens the overview. A worktree saves its exact folder association.
Capture workspace/vault/Objective and checkout identity before selection;
cancel on navigation or worktree-list changes. Persist the captured association
to its original workspace even if navigation happens during creation. An
association save failure must preserve and open the already-created session.

This updates workspace-terminal-folder-is-fixed.md for Objectives workspaces.
Other workspaces retain root/pinned-folder choices; restored sessions keep
their original cwd and processes. The Home demo uses the same three categories
and displays/simulates the selected launch folder accurately.
