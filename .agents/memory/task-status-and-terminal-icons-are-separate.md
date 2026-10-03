# Task status and terminal icons are separate

The user's latest October 3, 2026 icon preference supersedes the intermediate
bell proposal: show read-only ⬜ / ✅ status on the left of sidebar task rows,
and the task's chosen asset icon on the right. The right icon is inherited by
the active tab and linked terminals. Without a saved choice, it also follows
the task's checkbox status. Attaching or editing assets must not implicitly
choose their icon. Only dragging an asset onto the task's right icon area
chooses it and attaches that asset if needed. Keep existing explicit choices;
detaching the chosen asset restores the default status icon. The same behavior
applies to the Home demo. The staging seeder must not initialize asset icons.
