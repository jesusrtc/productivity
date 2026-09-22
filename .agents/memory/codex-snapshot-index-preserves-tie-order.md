# Codex snapshot lookup must preserve timestamp ties

A named projected thread's snapshots cannot improve its `MAX(ts)` candidate,
so a large recent-log window may skip those rows using the provider's existing
thread/time index before reading log records. Keep unprojected AND untitled
threads: both can represent a just-cleared conversation. Never mutate provider
indexes. Older schemas and small recent windows retain the timestamp lookup.

When changing scan indexes, explicitly preserve `(ts DESC, ts_nanos DESC,
id DESC)` order. Ordering only by seconds makes equal-second `/new` snapshots
choose different conversations depending on the index. Randomized equivalence
tests caught this regression; keep their multi-process and tied-time cases.
