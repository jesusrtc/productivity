# Terminal tabs follow Objective task order

The user requires automatic terminal-tab order within each Objective: whole
Objective assignments first, then parent tasks and their subtasks in the exact
sidebar task order, then terminals without an assigned task (including generic
asset/folder links). Keep the relative order of multiple terminals for one
task. A new subtask's terminal belongs below its parent, even across different
launch folders. Derive this on each render from canonical task IDs and saved
session UUID mappings, rather than writing a second task-order preference.

This supersedes worktree-first grouping in
objective-terminal-groups-use-flat-native-rows.md. Keep native flat pills,
Objective headers and status icons; show folder spacing only between consecutive
runs. Number pills in their displayed order. Preserve session metadata, tmux
identity, launch folders, conversations and input.

Whole-Objective assignments are terminal mappings without a resource/task/file/
folder target; the Tasks collection is also Objective-level. Support Objective
name ↔ terminal-name drops and reopen the overview. Console drops remain unsent
full-context pastes. The Home demo follows the same ordering and associations.
