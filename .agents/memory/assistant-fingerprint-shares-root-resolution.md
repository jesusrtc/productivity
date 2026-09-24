# Assistant fingerprints share only the resolved root

The snapshot fingerprint was resolving the same Assistant root for every file.
It now captures `root.resolve()` once per scan and supplies `resolved_root` to
`records.safe`. Every source still checks lexical containment and each component
for symlinks, resolves its current target, and reads current mtime/ctime/size.
There is no cross-request path/stat cache or skipped file validation.

Treat the captured root as a hint. If a source is outside it, resolve the root
again and run the original containment check. A root alias may legitimately move
during a scan; the first prototype rejected that transition and was corrected
before commit. Standalone validation keeps its original behavior. Tests preserve
fragments, missing paths, symlink rejection, fresh metadata and whole responses
across storage generations, including a mid-scan alias move and escaped fallback.

On the 500-note fixture, the coarse fingerprint median fell from 77.92/42.24 ms
elapsed/thread CPU to 68.79/35.76 ms. Those are preliminary diagnostic values,
not a guarantee for every request. The final code passed 155/160 native actions
across two unprofiled runs, retaining five slow Assistant opens (maximum 282.1 ms).
Its final 21 complete HTTP reads passed 200 ms, median 60.22 ms, first/max 107.11 ms,
fresh edit 91.48 ms. Do not erase the failed run because the repeat passed.
See the root-resolution checkpoint in `docs/performance-progress.md`.
