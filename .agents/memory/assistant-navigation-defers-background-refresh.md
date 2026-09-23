# Assistant navigation finishes before an overlapping background refresh

Assistant mtime events, WebSocket index updates and the five-second poll used
to start a new request generation during the initial view/document read. This
could discard the click's first result and defer rendering until another read
finished. The natural 500-note control retained a 279 ms example with two reads;
the prior checkpoint retained a 362 ms example where both requests were <200 ms.

Mark only those background callers with `backgroundRefresh`. While the current
`open` refresh is pending, they share one queued fresh read that starts after
initial rendering, legacy note-file loading and deep-link opening finish.
Preserve the request generation, section and active-view guards. Explicit user
refreshes, saves and later navigation remain immediate; older completions must
not clear a newer navigation owner. An initial error releases the queued retry.
Do not cache the initial response as the follow-up, drop changes or slow polling.

The complete 500-note/100-subtab native workload still includes 5,000 mixed files
and 2,500 Git changes per workspace. At a controlled 20 ms overlap, Assistant
entry misses fell from 20/20 to 4/20 and median from 265 to 184 ms. Each injection
must overlap the first request; late/missed deliveries stay failures. This is
not a watcher-delivery measurement. Two ordinary candidate runs passed 150/160
clicks, retaining nine slow Assistant entries and one 238 ms workspace return.
The overall latency goal remains open; do not combine injected/diagnostic runs
with the ordinary samples or claim physical input/display parity.
