# Assistant index shares current records

The Assistant index now captures one validated schema-2 record list and passes
it explicitly as `record_rows` to task, meeting, series, document and plain-note
projections. Projects filter that same list. No global or cross-request cache
was added; the next request still fingerprints current files. Standalone
projection calls default to a fresh read. `None` means read fresh; an empty
supplied list must stay empty without reloading.

Keep projections read-only and preserve sorting, descendants, progress, raw
assets, body handling, custom fields and workspace/series references. Schema-1
paths keep their existing logic. Retain the projects fallback when a migration
finishes after the initial legacy read and there is no captured record list.
Tests compare whole responses with independently read projections, check that
the shared list is unchanged, and cover all storage generations and fresh roots.

The 100-note HTTP median fell from about 56 to 17 ms. Two loaded native runs
passed 160/160 clicks; Assistant entry maxima were 104 and 112 ms. Restoring
the previous checkpoint brought back two >200 ms entries. Preserve the entire
workload, first samples, exact content checks and normal polling.

Larger collections remain open: the 500-note/100-subtab complete HTTP probe
missed 200 ms on 16/21 responses (median 203 ms, first/max 296 ms, fresh edit
283 ms). All contents were correct. Investigate remaining projection/traversal
costs without restoring repeated filesystem snapshots or narrowing the fixture.
