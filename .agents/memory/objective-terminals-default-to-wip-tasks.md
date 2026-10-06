# Objective terminals default to WIP tasks

In Objective workspaces, terminal tabs show only tasks whose existing status resolves to In progress (`in_progress`) by default, including recommended primary rows and extra child terminals that inherit that task's context. Todo, Completed, global and unassigned terminal tabs stay hidden; their processes and durable session/hierarchy/association identities remain intact.

Global Settings → Terminals has a browser-persisted “Show only In progress task terminals in Objectives” checkbox (`labTermWipOnly`, default true). Disabling it reveals every existing terminal and recommended global/task row. Keep Objective group headers and the New-terminal control visible even when no tasks are WIP. Other workspace/Home/document-only views retain their usual tabs.
