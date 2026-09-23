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
