# Filesystem polls are bounded

Workspace file listings and mtime polling share core.workspace_scan.walk. Preserve
linked-folder contents, but track ancestor device/inode pairs: a symlink to a Git
ancestor resets the old per-checkout depth budget and can defeat the recursion
limit. Close scandir iterators before descent and use each entry's cached stat.

Workspace Files/mtime now use background snapshots; see
workspace-files-use-background-snapshots.md. Other identical read-only polls use fsguard operation_key to share in-flight work. Keys
remain reserved after caller timeout until the worker really exits. Traversals
call fsguard.checkpoint between filesystem calls so abandoned work releases its
slot. Never do filesystem I/O while constructing timeout/exhaustion errors.
Bound subprocesses independently (tmux discovery uses a three-second timeout).

See docs/FILESYSTEM_NOTEBOOK_FAILURES.md for the September 2026 investigation,
including remaining uncertainty about the historical client's storage state.
