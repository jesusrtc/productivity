# Moving and deleting Objective tasks

Drag a task title or sidebar task onto the upper or lower half of another task
to move its branch above or below that task. An insertion line marks the drop.
Alt-drag opens **Make subtask**, **Move above**, **Move below**, and top-level
placement options. Drop a task on the full-width **Tasks** header to make it a
top-level task. The whole branch moves together, including deeper subtasks.

Each task owns an invisible contiguous block of terminal tabs in canonical
sidebar order. Moving the task moves its block and its subtasks' blocks. Tabs
may reorder individually within their own block, including inherited children;
terminal dragging cannot move, reparent or reassign a task. Saved order inside
each block survives task moves and browser reloads. Parent relationships still
supply inherited context and recovery without controlling block placement.

Moves retain task IDs, Markdown subtab IDs, assets, terminal identities, working
directories and running processes. Terminal blocks follow the new task hierarchy;
extra subterminals retain their existing task context. Cycles and incompatible repeat
schedules are rejected. Existing two-level task files need no migration.

**Delete** is available on task rows, task detail headers, and the sidebar's
task context menu. The first dialog lists the branch, terminal count and owned
files to remove. **Continue** opens a separate confirmation requiring the exact
task name. The final **Delete permanently** button stays disabled until it
matches. Canceling either step keeps the task.

Confirmed deletion removes the task and all nested subtasks, exclusive asset
registrations, owned documents/notebooks or selected task tabs, primary and
inherited extra terminals, saved terminal entries, Lab request history, and
automation launch records. Fixed mains and terminals owned by surviving tasks
remain. Shared assets and sibling/unrelated document content remain; surviving
document tabs are reparented out of deleted tabs.

External file/document sources and worktree folders remain intact. Their task
associations disappear. Provider conversation archives remain at their source.
Lab does not delete files inside a referenced worktree through this operation.

The server requires the reviewed registry revision, an owned-content review
token, confirmation and the exact task title. Changed content requires another
review. Running notebooks block deletion. Exclusive files are staged and shared
document edits backed up before cleanup; failed cleanup or registry writes
restore the task content. A terminal already stopped by a failed later write
stays stopped.
