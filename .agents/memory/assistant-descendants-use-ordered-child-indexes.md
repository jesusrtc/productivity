# Assistant descendants use ordered child indexes

Repeated descendant scans made the 500-note/100-subtab Assistant index quadratic.
Build a source-order child index from the current rows and pass it explicitly to
`descendants`. Preserve sibling batches, the reverse stack frontier, row identity,
full search content and cycle/duplicate errors. `None` keeps the original scan;
`{}` is an explicitly empty index. Malformed or unhashable parent keys fall back
to scanning so unrelated invalid references retain their original behavior.
Do not persist indexes across requests or parent edits.

Validation, progress and task/document/note projections now reuse local indexes.
The complete 500-note HTTP median fell from 203 to 64 ms; all 21 candidate reads,
including cold and externally edited content, passed 200 ms. Keep the native
failures: two loaded runs passed 152/160 actions, with six Assistant entries and
two first workspace returns over budget. The 362 ms Assistant entry overlapped
two individually sub-200 ms requests; inspect refresh ownership separately.
All content, normal polling, first samples and workload sizes remain required.

Tests preserve original scan results/errors across random trees and malformed
inputs, compare whole responses across storage generations, and bound repeated
parent lookup work. See the 2026-09-23 descendant-index checkpoint in
`docs/performance-progress.md` for complete results and remaining failures.
