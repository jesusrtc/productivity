# Sidebar file settings are workspace-scoped

Every preference in the File sidebar settings modal is browser-local but keyed
by the active workspace's normalized absolute path. This includes hidden files,
recent-file filters, added folder scopes, root colors, worktree folders, and
selected folders/worktrees. Framework Home and each vault root get their
own synthetic-workspace scopes too.

Never restore a single browser-global config for every workspace. New workspaces
start from the shared code defaults. The legacy `labSidebarFileConfig-v1`
record may migrate once to the first real (non-Home, non-vault) workspace
opened after upgrade, then all other scopes remain independent.
