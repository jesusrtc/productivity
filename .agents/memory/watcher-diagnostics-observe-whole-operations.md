# Watcher diagnostics observe whole operations

The isolated navigation fixture supports `--trace-watchers` and
`--trace-file-scans`, both requiring `--server-timings`. The first records
whole snapshots/diffs, watch refreshes and index rebuilds with elapsed and
thread CPU time. It is bounded under concurrent callbacks, omits paths/data,
and restores patched methods on exit. The second excludes per-notebook pending
lookups from the existing file trace to reduce observer overhead.

Keep polling, event delivery, rebuild and GC policy unchanged. Correlate worker
intervals by time/thread, since raw filesystem workers do not inherit request
context IDs. Overlap is evidence of concurrent work, not proof of causation;
do not sum nested observations or call the diagnostic a final latency run.

The 500-note Assistant diagnostic at `/tmp/lab-assistant-phases-before-server.json`
found two 5,051-entry watcher snapshots overlapping each of two >200 ms handlers.
They each consumed about 41–44 ms thread CPU over 143–152 ms elapsed, while the
Assistant handlers consumed about 119–121 ms CPU over 201–202 ms. The intervals
are not additive. Preserve this as a concrete next investigation, not proof of
causation or permission to reduce polling, scopes, debounce or freshness.
The existing optimized snapshot is in `core/src/core/polling.py`; do not repeat
its already-retained DirEntry/path-map changes. Correlations are saved in
`/tmp/lab-assistant-boundary-watcher-overlap.json`.
