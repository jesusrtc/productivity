# Concurrent cProfile results need consistency checks

On the tested Python 3.14 build, starting a per-request cProfile session in each
of two concurrent search handlers raised `ValueError: Another profiling tool is
already active`. A nonblocking guard profiled only one handler while leaving the
other request running, but the resulting function timings were inconsistent:
one poll row reported 87.83 ms self time and only 2.13 ms cumulative time.
Do not interpret those function costs or infer a root cause from them.

Keep failed/perturbed runs in the evidence, then use coarse per-request wall and
thread-CPU timers plus unprofiled complete HTTP controls for optimization claims.
Never serialize the measured requests to make a concurrent profile work.
Evidence: `/tmp/lab-code-search-capture-profile{,-fixed}-{http,server}.json`
and `docs/performance-progress.md`'s complete-capture decoding checkpoint.
