# Capped search keeps complete process output

Code search returns at most 500 matches, but ripgrep can emit many megabytes
before the parser starts. Iterate the nonempty `str.splitlines()` pieces lazily,
preserving every recognized boundary, instead of allocating every output line.
On the 5,000-file/100,000-match fixture this removed about 14.7 ms of parsing and
32 MB of transient allocations. Full HTTP requests still exceeded 200 ms;
never equate parser timing with endpoint or browser timing.

Keep the original stdout/stderr pipes, full process completion, strict text
decoding and timeout behavior. Worker tuning requires separate dense, sparse,
regex and concurrent-client evidence; see the literal-search worker-policy note.
Redirecting stdout to a temporary regular file looked faster, but lost output
when a PATH-selected wrapper exited before a descendant that closed stderr and
wrote stdout later. Waiting for the parent and stderr EOF is insufficient.
The native regression in `test_code_search_capture.py` preserves this case,
plus invalid bytes beyond the result cap and timeout child cleanup.

`lab_code_search_latency.py --repos 1 --search-files 5000` exercises the complete
authenticated HTTP route with normal server lifecycle/watchers. Preserve all
samples, exact row/snippet and freshness checks, and fixture/server cleanup.
The Code Search UI remains a placeholder; this is backend evidence only.
