# Terminal recent activity is selection-local

The terminal rail's recent state means the user selected the tab or just left
it; it does not mean the tmux process merely exists. Record activity both on
attach and detach so a tab that remained selected for hours is still recent
when the user moves away.

Persist recent timestamps as browser-local navigation state, scoped by
vault plus workspace/pseudo-workspace. The highlight window is also
browser-local, defaults to 60 minutes, and uses preset choices in the terminal
settings modal: 15m, 30m, 1h, 3h, 6h, 12h, or 24h. Persist the user's marker color
there too; the native color input deliberately allows any six-digit hex color.

Keep the selected tab's existing blue treatment. Inactive recent tabs show a
slim 3px vertical line on the left edge in the configured recent color (green
by default). Retain `labTermRecentDotColor` for compatibility with saved color
preferences. Do not tint the tab background. Folder/worktree badges identify
the linked scope independently of recency.
