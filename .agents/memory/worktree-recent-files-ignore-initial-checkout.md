# Worktree time filters ignore the initial checkout

For linked worktrees, Recently updated should ignore untouched files written
by `git worktree add`. Recover the initial commit and checkout completion from
the first two entries in the worktree's own HEAD reflog. Never move this baseline
to a later commit/reset or use the time Lab first sees the worktree.

Reflog times have second precision: within that initial second, compare with
the initial commit so immediate edits and already committed changes survive.
Files saved later and new paths retain normal mtime behavior. If the original
record is unavailable or Git fails, leave files visible. Initial records older
than the maximum 24-hour selector need no Git comparisons.

Detached HEAD can omit the initial no-op reset record. When its creation commit
is known but completion time is not, suppress paths that still match the initial
contents. This fallback does not treat a save of identical contents as an edit.

Annotate checkout-generated files instead of changing their timestamps or
removing them from Files. Only the time filters use the annotation; Git scopes
and notebook modification markers preserve their existing semantics. Detect
linked repositories inside wrapper folders and when browsing their subfolders.
