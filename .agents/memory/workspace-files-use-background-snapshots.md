# Workspace files use background snapshots

Files and mtime share workspace_snapshot.Store per vault, lexical path, and dotfile
setting. Do not wrap a whole workspace scan in fsguard's ten-second request timeout:
a healthy large traversal loses all progress and never returns a usable listing.
Use bounded background workers, a short request wait, 202/Retry-After for the first
snapshot, and the last complete listing while refreshing. The browser must collect
202 responses without publishing an empty list or starting a replacement scan.

Keep this pool separate from small guarded reads. Report stalls with operation,
path, visited count and idle time, and preserve the last success on a failed refresh.
Notebook running flags are read from memory; resolve their paths in the scan worker.
Use the snapshot revision as well as mtime so deletions trigger refreshes.

See docs/FILESYSTEM_NOTEBOOK_FAILURES.md for the September 23 follow-up and validation.
