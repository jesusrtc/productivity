# Sidebar file settings are project-scoped

Every preference in the File sidebar settings modal is browser-local but keyed
by the active project's normalized absolute path. This includes hidden files,
recent-file filters, added folder scopes, root colors, worktree folders, and
selected folders/worktrees. Framework Home and each workspace root get their
own synthetic-project scopes too.

Never restore a single browser-global config for every project. New projects
start from the shared code defaults. The legacy `labSidebarFileConfig-v1`
record may migrate once to the first real (non-Home, non-workspace) project
opened after upgrade, then all other scopes remain independent.
