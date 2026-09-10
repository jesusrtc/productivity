# Terminal project/worktree links coexist with file links

New terminals (including agents) capture the selected sidebar folder/worktree
as durable `linked_scope` metadata and start in its root. Projects without
worktrees use their folder directly. Restoring a saved terminal reuses that root.
The worktree picker's “Link current terminal” action changes the association
only; it never sends `cd` or restarts a running command or agent.

File linking cascades to the file's project/worktree association. Removing the
file link leaves `linked_scope` intact. Terminal clicks restore the sidebar scope
and optional file only when the existing browser-local Sync linked switch is on.

Terminal tabs use the worktree color (project folder color for main), with a
left-edge accent. Recent inactive tabs use a green background tint (or the
user's configured recent color); preserve the active tab's blue treatment. Colors follow local sidebar
settings, falling back to the color saved with the scope in other browsers.
