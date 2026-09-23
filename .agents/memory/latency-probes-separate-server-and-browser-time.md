# Correlate browser requests with isolated server timing

The navigation/typing fixture accepts `--server-timings /tmp/result-server.json`
and optional `--trace-sessions`. Browser API records carry absolute start time
and workspace scope; the sidecar measures ASGI entry through final response
body and the synchronous terminal-listing handler separately. Function tracing
also records worker identity, including calls on fsguard workers. No request
bodies, cookies, or arbitrary query parameters are recorded.

ASGI timing excludes socket acceptance and event-loop delay before app entry.
Browser ResourceTiming is therefore not interchangeable with endpoint execution
time. Nested/concurrent function durations are wall times and must not be summed.
Keep failed samples and use matching route/scope/start times to diagnose outliers
before changing production behavior. This instrumentation runs only in the
isolated fixture; it does not alter production responses or the user's server.

The fixture now opts into a `Server-Timing: lab-perf` description containing a
request ID. Browser ResourceTiming records expose that ID, matching the ASGI
sidecar exactly even when requests overlap. Default diagnostics preserve headers;
the opt-in header is appended without changing existing headers or response
bodies. Handler/function rows inherit request IDs through ContextVars where the
runtime propagates them; bare fsguard worker threads do not inherit that context.
`--trace-files` times file-list/mtime handlers, guarded operations, pending
lookups and awaited FastAPI serialization. Treat those traces as diagnostics;
use untraced browser runs and alternating route/ASGI comparisons for performance
claims. The file-scan comparator supports notebook extensions and swaps the
baseline's original pending helper only between completed sequential samples.
