# Empty notebook pending state needs no filesystem identity lookup

`nb_exec.is_path_pending` checks `_pending_paths` under its existing lock before
resolving the target. If the registry is empty, no notebook can match, so it
returns false without path/symlink resolution. An active registry still uses the
original resolved-path lookup under the lock; queued run counts, aliases and
retargeted links remain live. Do not replace it with a cached filesystem or
per-request pending snapshot that hides changes during execution.

Resolving every inactive notebook used 21–50 ms per mixed 5,000-file scan in an
isolated trace. Alternating full ASGI comparisons for 5,000 notebooks reduced
median time from 108.1 to 20.0 ms while preserving every response field. This
does not establish browser typing latency or optimize the nonempty-registry case.
