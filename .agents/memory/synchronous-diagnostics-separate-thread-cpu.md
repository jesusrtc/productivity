# Synchronous diagnostics separate thread CPU from elapsed time

The optional isolated ServerTimings function/handler wrappers record
`threadCpuMs` only for synchronous calls. Elapsed `ms` includes waits; thread
CPU helps distinguish computation from filesystem, scheduling or lock delays.
Both include nested work and must not be summed across nested observations.
Async calls omit thread CPU because unrelated tasks can execute during awaits.

The guarded file worker and its waiting request handler are different threads:
a ~28.5 ms scan used ~20 ms worker CPU, while its waiting handler used <1 ms.
This diagnostic did not reproduce the earlier ~91.5 ms cold file response, so
it does not establish that the rare delay was fixed or identify its cause.
Detailed per-notebook observers add allocation/CPU work; use ordinary request
timing for final latency claims and keep producer/worker observations separate.
