# Registered projects seed each browser's sidebar

Workspaces registered through `lab workspace add` must expose their project
buttons on an ordinary workspace open. Derive project roots, labels, and worktree
parents from the workspace's worktree registrations; do not rely on a setup page
or preferences injected into an agent's test browser.

The browser imports each registered project once per workspace. Preserve custom
labels, colors, filters, and unrelated folders, and remember imported paths
separately so intentionally removed buttons do not return on reload. Preferences
remain browser-local and isolated by workspace path. Repository cards use project
names because worktrees of different projects can share the same directory name.

Live verification must start at the normal workspace URL with no seeded browser
storage. A configured automation profile alone does not establish that the user's
browser has the same project buttons.
