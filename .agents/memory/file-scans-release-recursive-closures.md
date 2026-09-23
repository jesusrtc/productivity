# File scans must release their recursive closures

`api_workspace_files` builds a request-local recursive scanner. Calling that
inner function through its own captured name creates a reference cycle that
retains the complete file list and workspace path after a successful request.
Large repeated scans then leave cyclic GC to reclaim whole batches, pausing
terminal input even when the scan runs on a filesystem worker.

Pass the recursive callable explicitly so the function does not capture
itself. Preserve traversal order, fresh metadata, checkout annotations and
the guarded-worker lifetime. Do not clear the callback from the request's
`finally`: a timed-out filesystem worker may still need to finish recursion.

A regression uses weak references to request paths with automatic GC disabled
only inside the test; a completed scan must release them through normal
reference counting. Production GC policy is unchanged. Passive fixture GC
and terminal traces can distinguish collector pauses from browser rendering
or PTY delays; keep failed input samples and measure without detailed tracing
before claiming end-to-end latency improvements.
