# Polling snapshots reuse native entries and completed path maps

Lab's polling observer keeps watchdog's schedule, fresh reads, event diff and
queue. Its private snapshot uses each fresh `DirEntry.path`/`stat()` directly,
avoids a per-entry context manager, and retains only directories for recursion.
Custom stat/listing adapters retain the upstream traversal. Enumeration/stat
failures, followed links, recursive/non-recursive coverage and traversal order
must remain equivalent.

The private completed snapshot exposes a dictionary key view to watchdog's
unchanged set operations instead of copying every path set repeatedly. It is
never mutated after construction. Keep this confined to the private polling
snapshot; do not change the public watchdog class or mutate its path map.

An 80-sample alternating component run on 5,000 files reduced scan median
15.72 → 12.73 ms and diff median 3.51 → 2.98 ms, verifying paths, inode maps
and event-detection fields. Native file/dir mutation, link, replacement,
permission, disappearing-entry and live polling/WebSocket tests protect event
equivalence. Keep the normal polling interval, watch scopes and debounce.

The earlier 83.43 ms file response overlapped two large watcher snapshots;
its 73.32 ms worker used 32.09 ms thread CPU, without a significant GC pause.
The paired candidate cold request had no snapshot overlap, so its lower time
alone cannot prove the old cold-navigation outliers are eliminated.
