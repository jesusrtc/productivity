# Repository summaries share bounded Git workers

`GET /api/code-search/repos` reads branch and last-commit metadata afresh for
every repository. Serial subprocesses made a 20-repository response take
roughly 500 ms. A shared eight-worker executor reduces measured responses to
roughly 110–120 ms while preserving case-insensitive catalog order via `map`.

Keep the bound shared across requests, not one pool per browser/request. Each
worker runs the existing two Git commands in order, with their original
timeouts, parsing and empty/detached/failure fallbacks. Single-repository
requests share the bound too; an empty catalog starts no workers. No metadata
cache is involved. Tests must exercise
out-of-order completion, concurrent requests, worktree pointers and fresh data.

`scripts/perf/lab_code_search_latency.py` uses a disposable CLI-created vault,
normal authenticated server lifecycle, real repositories, and a branch/commit
mutation. Keep every timing, including first requests and failures. Its HTTP
completion measurements are not Code Search UI paint timings. The UI entry
is currently a placeholder; do not claim a measured browser interaction gain.
