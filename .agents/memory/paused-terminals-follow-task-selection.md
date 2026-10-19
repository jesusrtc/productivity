# Paused terminals follow task selection

On October 19, 2026 the user clarified that the default right terminal rail
should show In progress task terminals and generic workspace/Objective terminals.
A paused task is the exception only after explicitly selecting it. Pausing the
current WIP task hides the group immediately; mark deliberate paused selection
on the saved focus instead of treating an existing WIP selection as an exception. Leaving
for another task, Tasks or the Objective overview hides its terminals immediately,
including inherited children and previously active consoles. Task clicks and
`lab ui command task-open` reuse its existing primary; missing terminals still
follow the workspace task-terminal setting.

Notification highlighting must reveal only its exact destination temporarily.
It must never persist Show all for an entire Objective. Old per-Objective
overrides reset once via terminalFilterVersion 2 because prior automatic and
manual overrides are indistinguishable; subsequent explicit choices persist.

This supersedes the selected-paused exclusion in
`task-terminal-status-overrides-selection.md`, `inactive-task-terminals-expire.md`
and `cli-task-navigation-shares-terminal-policy.md`. Other inactive task statuses
remain filtered by default; the automatic retention windows are unchanged.
