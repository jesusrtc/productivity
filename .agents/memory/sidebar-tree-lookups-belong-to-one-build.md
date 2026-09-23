# Sidebar parent lookups belong to one build

`buildSidebarTree` serves the workspace, Recent, vault and framework trees.
Repeatedly splitting and walking the same parent folder was a measurable part
of large-sidebar refresh CPU time. Reuse parent nodes in a Map local to that
single build; discard it when the function returns. Do not turn this into a
cross-refresh or cross-workspace cache.

Directory metadata is applied first, including later entries for the same
folder. Populate the lookup during the file pass, after metadata is complete.
Keep original file objects and ordering, directory/symlink metadata, name
fallbacks and empty folders. Leading, repeated and trailing slashes retain
the previous normalization; `..` remains a literal tree segment.

The focused tree tests check those semantics and fresh builds after removals.
Existing real-Chrome sidebar tests cover rendered geometry, native actions,
fragment reuse and cache bounds. Component timing is distinct from terminal
input-to-render latency; a faster build does not prove every key meets 50 ms.
