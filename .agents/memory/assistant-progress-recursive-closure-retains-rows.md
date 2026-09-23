# Assistant progress recursion retains rows until cyclic GC

A post-benchmark weak-reference probe of `assistant_records.progress_map` proved
that its self-referencing nested `visit` closure retains input rows after the
function returns. With automatic GC disabled only in the probe, a weakly
referenced dict subclass remained alive after deleting input/result, then died
after explicit collection (17 objects collected). Production GC was not changed.

This is an outstanding retention issue, not an established cause of the native
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
