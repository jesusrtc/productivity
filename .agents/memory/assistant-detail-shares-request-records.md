# Assistant detail reuses only the current request's records

A modern document detail read previously loaded the complete library three
times: initial resolution, tree/progress construction, and document-task
resolution. Each load performs a fresh fingerprint even when parsing is cached.
For 500 notes, those duplicate scans dominated the detail handler.

`assistant_v2.detail` now lazily captures the initial resolution's complete
records and supplies them to task resolution. The lazy iterable starts only
after reference validation; invalid paths still fail before scanning files.
Filtered legacy collections retain their original validation order. An
explicitly supplied empty iterable is not a request for a fallback read.

This is reuse within one request, not a cross-request cache. `records.resolve`
still checks the selected source path and reads its current metadata/body;
task views still validate the physical document and compute its raw revision.
Every next request refreshes the library normally. Keep traversal and symlink
rejection, collection errors, alias matching, full trees, and fresh external
edits in regression coverage.

The complete 42-read HTTP diagnostic reduced snapshot/fingerprint calls from
126 to 42 and median unchanged detail completion from 76.06 to 27.16 ms. This
does not establish all native clicks below 200 ms; the browser workflow also
includes document-terminal admission, process startup, attachment, and render.
Use `scripts/perf/lab_navigation_latency.py --assistant --assistant-details`
for that workload. Its terminal is a labeled owned echo CLI on a private tmux
socket, not a real agent startup or an iTerm/physical-display comparison.
