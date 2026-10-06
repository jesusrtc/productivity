# Terminal subtabs use hover and an explicit drop choice

Dropping a terminal tab onto another asks Move below, Make child, or Cancel.
The drop does not write until a choice is made. Make child selects the dragged
terminal; its parent reveals children on hover and keeps the active child
visible while using the console. Support nested descendants and moving an
entire subtree. Remove from parent tab is available in the child's context menu.

Parent links and explicit below placements live in the existing browser-local,
vault/workspace-scoped terminal group state (`tabParents` and `tabAfter`).
Preserve session identity, launch folders, task assignments, conversations and
input. Prevent cycles and cross-Objective parent links. Closing a parent reveals
its surviving children as independent tabs. Objective task order is the default;
an explicit Move below placement overrides it for the moved tab.

Unchanged polls preserve hovered nodes. After changed markup, restore hovered
branches and close inactive branches when leaving the stable rail. The Objective
resource-drop handler must let terminal-to-terminal drops reach the rail handler.
Native disposable Chrome checks cover both orientations, hover, cancel, selection,
Objective headers/dropdown, ordinary rails, reload and preserved identities.
