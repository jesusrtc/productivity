# Worktree tabs use the folder/worktree identity

For a terminal linked to a worktree, show the agent icon and colored
`folder alias/worktree-name` as the only tab label. Omit session names,
including custom names, and the redundant literal `worktree` badge.
Without a folder alias, show just the worktree name. Give the label all
available row width; retain full details in the tooltip and keep compact
icon mode. Main-checkout terminals keep their existing session labels.

This supersedes the worktree indicator in `terminal-tabs-use-folder-badges.md`.
