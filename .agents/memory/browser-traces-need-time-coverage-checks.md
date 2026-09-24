# Browser traces need time coverage checks

Do not assume a successfully saved Chrome trace covers the full workload.
The verbose Blink/invalidation trace of the 1,500-section document workflow
contained ~813,000 events and 323 MB, but covered only the first ~5.9 seconds
of a ~66-second CPU profile. It cannot explain a later failed input sample.
Check the actual event time range against externally recorded input epochs.
`inputSetups` includes sample IDs and start/end epochs for this correlation.

Verbose tracing also made 97/140 clicks miss the budget in that diagnostic
run. Use it to locate work only within its coverage, and retain a separate
run without detailed tracing for latency claims. Native time reported as
`(program)` is not evidence of a particular Lab handler or Chrome subsystem.
