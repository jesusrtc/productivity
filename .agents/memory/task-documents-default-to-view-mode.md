# Task documents default to View mode

Task-mode Objective-owned Markdown must open as rendered read-only content.
A separate View/Edit switch beside Off/Semi/Focus explicitly enables the native
Markdown editor. Return to View after three minutes without document, header
or owned edit-dialog activity, including scrolling the document container.
Reset permission on task/subtask navigation or reopening; do not persist Edit.

View removes the editor surface and disables Markdown checkboxes, Rename,
Save/Revert/new-subtab and the task header's completion, icon drops and Edit task.
Retain the same editor instance, undo and draft when switching modes. Flush
pending authorized edits on View/navigation; save conflicts retain the visible
unsaved draft and stop retries. An idle edit dialog locks its fields and submit
button while retaining entered values and allowing Cancel.

Ordinary Objective Markdown outside task mode and linked native assets retain
their existing editors. The Objective Show all terminals control must preserve
the open draft and View/Edit state; it is a filter, not document navigation.

The focused native-browser regression advances only the permission timer and
checks read-only controls, scrolling, draft saves, task/subtask navigation,
modal locking, conflict recovery and ordinary document editing. The full API
regression also verifies task View/Edit alongside native save/navigation flows.
