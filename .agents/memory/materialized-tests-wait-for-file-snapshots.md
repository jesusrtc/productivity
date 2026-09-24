# Materialized test reads wait for refreshed file snapshots

The production Files store returns the last complete snapshot immediately while
refreshing. Invalidating its index does not make that response synchronous.
MaterializedClient must poll the underlying client, without invalidating again,
until the scan state leaves scanning/queued/refreshing, with a bounded timeout.
Otherwise tests can assert old metadata after an edit or deletion. Tests of the
actual 202/cached-response contract use client._inner and keep their nonblocking
assertions. Never change production cache semantics to satisfy materialized tests.
