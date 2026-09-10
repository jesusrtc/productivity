# Terminal metadata closes SQLite connections

Wrap read-only SQLite connections in `contextlib.closing`: the SQLite
connection's own context manager ends a transaction but does not close the
connection. Do not rely on garbage collection to release database handles.

Repeated Codex terminal metadata polling exhausted the macOS server's 256
file-descriptor limit, retaining handles to the state, logs, and history
databases and causing HTTP 500 errors and supervisor failures. All Codex and
Copilot lookup connections in `core/src/core/routes/term.py` must close on
success and query errors. The metadata tests retain connection references and
verify closure explicitly so garbage collection cannot hide regressions.
