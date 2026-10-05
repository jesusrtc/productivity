# Task status and terminal icons are separate

The read-only two-state rule below is superseded by
[Sidebar task status menu](sidebar-task-status-menu.md). The separation from
custom asset icons and their drop behavior still applies.

The user's final October 3, 2026 clarification supersedes the intermediate
bell and duplicated checkbox proposals: show read-only ⬜ / ✅ status on the
left of sidebar task rows. Show the right-side icon only when the task has a
chosen asset icon; without one, leave it visually empty. Keep an empty drop
area, revealed on hover/focus, so an asset can still be dragged there.
The active tab and linked terminals use the chosen asset icon, or the task's
checkbox status when there is no custom choice. Attaching or editing assets
must not implicitly choose their icon. Only dragging an asset onto the task's
right icon area chooses it and attaches that asset if needed. Keep existing
explicit choices; detaching the chosen asset leaves the sidebar right icon
empty again. Apply the same behavior to the Home demo. The staging seeder must
not initialize asset icons.
