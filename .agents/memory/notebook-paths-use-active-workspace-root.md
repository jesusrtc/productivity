# Notebook paths use the active workspace root

The Lab framework checkout and the selected workspace can live under different
filesystem roots. `LAB_MONOREPO_ROOT` / `SELF_REPO_PATH` identify the framework
checkout for the Productivity self-view; they are not the base for workspace
files.

Render the active `index_cache.root` separately as `LAB_WORKSPACE_ROOT`, and
include that root in the cached index-shell key so workspace switches cannot
serve stale HTML. The notebook frontend must validate containment under that
active root and send a path without a leading slash. `/api/nb`, session,
execute, restart, and cell-delete routes intentionally continue to reject
absolute paths and traversal.
