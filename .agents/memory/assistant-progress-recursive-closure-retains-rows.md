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
