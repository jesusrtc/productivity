# File scan capacity is queued

A full snapshot worker pool is normal backpressure, not a file-read failure.
Keep two workers and at most 32 scopes; queue one job per scope, prioritize first
listings over cached refreshes, and start queued work when a worker completes.
Return 202/Retry-After for initial queued work (including saturated admission)
so the browser waits without an error toast. Cached snapshots return immediately
while refreshing, without the 150 ms initial-read wait. Keep genuine stall/error
diagnostics and bounded shutdown; queued work cannot unblock a stuck OS call.

FSEvents already invalidates affected directory metadata, with five-minute full
reconciliation and a thirty-second fallback when native watching is unavailable.
These caches remain in memory. This supersedes the earlier no-queue capacity
policy in the background snapshot notes; see docs/FILESYSTEM_NOTEBOOK_FAILURES.md.
