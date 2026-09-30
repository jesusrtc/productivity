# Guarded metadata lock waits must cancel

Guarded workers waiting for `_SESSION_METADATA_LOCK` used to survive their
caller's filesystem timeout. Use `fsguard.cancellable_lock` for guarded reads and
checkpoint between scan steps; timed-out lock waiters release their worker even
while the owner remains active. A timed-out caller cannot release a worker
blocked inside an OS syscall. Scoped terminal reads share discovery work but
copy returned rows before request-specific enrichment and sorting. Retain the
blocked-lock and concurrent-row-isolation regressions.
