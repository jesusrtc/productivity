# Assistant progress recursion must release completed trees

A post-benchmark weak-reference probe of `assistant_records.progress_map` proved
that its self-referencing nested `visit` closure retains input rows after the
function returns. With automatic GC disabled only in the probe, a weakly
referenced dict subclass remained alive after deleting input/result, then died
after explicit collection (17 objects collected). Production GC was not changed.

This was a retention issue, not an established cause of the native
Assistant latency tail. A follow-up can pass the recursive callable explicitly,
as with the prior file scanner, while retaining progress/order/error behavior.
Add a weak-reference lifetime regression and measure separately before claiming
latency gains. Do not disable production GC or narrow the complete workload.
Evidence: `/tmp/lab-assistant-tree-retention.json` and the descendant-index
checkpoint in `docs/performance-progress.md`.

A later full native diagnostic with passive GC callbacks observed 597 cycles,
210.99 ms total and 19.39 ms maximum. A 231.8 ms Assistant open overlapped 14.41 ms
of collection; a 249.7 ms open overlapped only 0.04 ms. Its handler elapsed/CPU
was 207.71/119.18 ms. Retention still exists, but GC alone does not explain the
remaining latency tail. Do not change production collection policy or claim
causality from retained objects alone. Artifacts:
`/tmp/lab-assistant-refresh-native-gc-{browser,server}.json` and
`/tmp/lab-assistant-refresh-gc-summary.json`.

The follow-up removes self-reference from all three helpers:
`assistant_records.progress_map`, `assistant_tasks.normalize`, and
`assistant_tasks.summary`. Each recursive helper takes its callable explicitly;
traversal, copying, status derivation and errors remain the same. Normalization
also retained copied tasks, and summary retained even an empty normalized list.
Five weak-reference regressions all fail on the old code and pass on the new
code. They temporarily disable automatic collection only in the test and restore
its prior state; production GC settings are untouched.

In matching 500-note full native diagnostics, passive GC recorded 590 versus
189 collections, 191.45 versus 58.30 ms total, and 853,877 versus 10,249 objects
collected. This proves reduced retained work, not improved native tail latency:
the candidate diagnostic still had five Assistant misses, including a 414.1 ms
first open with only 0.015 ms overlapping collection. Keep that failure and use
unprofiled runs separately. Evidence: `/tmp/lab-assistant-release-{before,after}-`
`{browser,server}.json`, the lifetime regressions, and the corresponding
checkpoint in `docs/performance-progress.md`.
