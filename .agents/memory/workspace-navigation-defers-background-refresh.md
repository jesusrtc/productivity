# Workspace navigation finishes before an overlapping background refresh

An index/mtime dashboard refresh can arrive while an explicit workspace click
is still reading its sidebar or dashboard. Starting another generation at that
point invalidates the click's pending result and makes its first paint wait for
the replacement read.

`showWorkspaceInfo` tracks the current explicit navigation by workspace, file
root and dashboard sequence. Background calls for that same owner share one
follow-up promise, preserving a copy of the latest requested options. The first
navigation finishes normally, then the follow-up reads fresh data. A new user
navigation remains immediate; a scope change or newer generation invalidates
the queued work. An older completion cannot clear a newer owner.

Keep the existing sidebar/dashboard race guards and fresh reads. This is not a
response cache and does not suppress changes delivered during the first read.
The existing background sidebar reconciliation still has its separate completion
semantics. Ordinary background refreshes outside explicit navigation retain
their existing behavior.

The isolated probe's `--navigation-refresh-delay 20` invokes the normal
background-refresh entry point during native clicks without disabling polling.
It is a controlled overlap experiment, not watcher/WebSocket delivery latency.
Count missed/late deliveries and report ordinary navigation and typing results
separately; a controlled comparison alone cannot establish the full latency goal.
