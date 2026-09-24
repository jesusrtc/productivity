# Project sidebars use disk snapshots and shallow directories

The user accepts about a minute of staleness for project/worktree navigation,
Uncommitted, vs local main, and recent commits, provided cached views appear
immediately and refresh in the background. Local-main must include staged and
unstaged edits. Keep exact base-to-working-tree semantics, including locally
reverted branch edits; do not replace the comparison with a simple union.

Project scopes use shallow folder reads and per-vault SQLite snapshots, not a
full recursive file scan on each click. Git work is bounded and serialized per
checkout; directory reads have a separate worker. Recent lists page at 200 rows.
Use the server snapshot age for browser expiry. Refresh only visible requested
scopes, preserve good data on errors, and keep cache/queue limits explicit.

All six requested real repositories and linked worktrees were measured. Cached
interactions passed 500 ms in the retained run, but first uncached Linux/LLVM
views still took 653/812 ms and LLVM's first time filter took 8.4 seconds. Do not
claim every cold interaction meets the budget. Evidence and reproduction live
in docs/diagnostics/large-project-sidebar/README.md.
