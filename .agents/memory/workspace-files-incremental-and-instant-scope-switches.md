# Files use incremental metadata and cached scope views

The Files and mtime snapshot store shares a native filesystem event index:
FSEvents on macOS, inotify on Linux, Windows notifications elsewhere supported.
Ordinary requests must not force full scans. Invalidate changed directory
metadata on events; directory mtime alone misses in-place child edits. Full
reconciliation handles missed events (five minutes, thirty seconds without a
healthy native subscription, adaptive rest for slow scans). Keep subscriptions
bounded/shared and prune removed symlink targets. No per-file kqueue watches.

Folder/worktree switches must feel instant (user target under 200 ms), for any
project. Cache actual sidebar DOM nodes, expansion/scroll state and discovery
per surface/workspace/folder/worktree/display settings, with bounded retention.
Restore before awaiting discovery, files, or Git. Capture the outgoing select's
old value before saving its nodes: onchange has already changed the DOM value.
Keep normal background refresh quiet and compare the displayed Files revision
with mtime polls to avoid stale trees when a scan completes during navigation.

Regression coverage: test_workspace_index.py, test_workspace_snapshot.py,
test_frontend_scope_switch.py and test_frontend_sidebar_file_config.py.
Chrome's 50,000-file fixture tests cached switch-to-frame latency; cold loads
still require an initial scan. See docs/FILESYSTEM_NOTEBOOK_FAILURES.md.
