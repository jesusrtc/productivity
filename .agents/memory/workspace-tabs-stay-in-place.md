# Workspace tabs stay in place

Workspace tab positions must not depend on activation, visit recency, or discovery
order changes during polling. Restore the saved order before painting the strip,
append newly opened workspaces, and change existing positions only on a completed
drag-and-drop. Keep closed tabs' saved positions for reopening. Use absolute
workspace paths for order and drag identity so equal names across vaults do not
collide. Active styling must not shift the tab's geometry.
