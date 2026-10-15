# Terminal tabs have only status dots

The user clarified on October 15, 2026: every terminal row shows its icon,
one vertically centered agent-status dot when reported, and its name. Remove
Home/folder labels, location dots, automation process dots, merged-tab dots and
extra main prefixes. Keep existing name/icon colors and location details in
hover context. Compact mode hides the name while keeping icon/status geometry
stable; expanded mode places the dot between icon and name.

Apply this to ordinary, worktree, task, recommended, automation and merged tabs.
Task/sidebar markers outside terminal tabs are unaffected. This supersedes the
location-marker presentation in terminal-tabs-show-only-saved-names.md and
terminal-status-diagnostics.md; their naming and diagnostic behavior remains.
