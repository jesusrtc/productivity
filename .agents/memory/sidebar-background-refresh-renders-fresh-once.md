# Background sidebar refreshes render fresh data once

`_refreshWorkspaceSidebar({backgroundRefresh:true})` is for mtime/index updates.
When cached data exists, keep the visible rows while fetching and render the fresh
payload once. Explicit navigation and settings retain their immediate cached
paint. Do not infer this behavior from `preserveScroll`: user actions also use it.

Render fresh payloads even when their file data equals the cache. Selection,
folder state, last-viewed notebook markers and the pending grace window can change
independently. A failed file read falls back to cached rendering only while the
same refresh generation, workspace and selected worktree still own the sidebar.
Forward the option through dashboard refreshes without duplicating its read batch.

The refresh promise still resolves before detached reconciliation finishes. The
typing probe reports dispatch time separately and verifies current file mtimes
and rendered recent ordering after its writes; dispatch time is not total refresh
latency. Keep normal polling and every externally timestamped key in comparisons.
