# Assistant notes share a listing snapshot

`assistant_documents.snapshot` still fingerprints every Markdown document on a
cache hit and returns a deep copy. Calling `records.records(root)` separately
for each note's descendant search text repeats those scans and copies. Keep one
local snapshot in `assistant_v2.plain_note_rows`; retain the existing descendant
traversal, note-type/embedded filters, order, fields and string conversions.
The next listing must take a fresh snapshot; do not cache the response across
requests or weaken filesystem validation.

The owned 100-note/20-subtab fixture reduced complete `/api/assistant` snapshot
reads from 108 to eight and single-client HTTP median from 615 to 56 ms. Every
first request and external-file freshness check is retained. That checkpoint
still had other snapshot consumers. The subsequent
[shared index read](assistant-index-shares-current-records.md) reuses one list
throughout each response.

Native Assistant Dashboard/All/Starred/workspace clicks run through
`lab_navigation_latency.py --assistant`. Readiness checks every displayed card,
identity, title, summary, star, task badge and section limit, with unchanged
Markdown verified after each cycle. A 5,000-file/2,500-Git-change workload still
missed 200 ms on four of 40 optimized Assistant entries (maximum 242.5 ms),
despite 149–166 ms browser p50s. Preserve these tails and normal polling; do not
describe the backend's isolated pass as an all-UI pass.

The custom-attributes browser test's save timeout reproduced with the original
endpoint restored. The remaining 189 focused checks passed with native browser
access; a sandbox-only run had nine Chrome-startup failures. This is a baseline
test limitation, not a fully green suite.
