# Reuse pristine folder fragments while rebuilding sidebar templates

Workspace Files and Recently updated renderers provide exact source offsets for
balanced folder elements. The template builder compares those ranges with the
previous pristine template and clones the largest unchanged folders through
temporary placeholders. Changed parents can still reuse unchanged descendants.
The assembled template has exactly the DOM of a complete parse, with no remaining
placeholders or live decorations. Literal placeholder-like content falls back to
a complete parse. Explicit navigation still mounts a pristine clone.

Keep fragment indexes as offsets plus references into the one retained template;
do not retain overlapping fragment strings or additional subtree copies. The
four-scope/60,000-element bounds still apply. A temporary clone/source identity
map can skip deep equality checks during one synchronous reconciliation, but must
never be stored in the cache because it would retain older templates.

If reconciliation only moves/deletes existing nodes, their Git decorations remain
valid and fresh cached styling need not be reapplied. New pristine nodes require
repainting; stale/missing Git data must still fetch and apply with scope guards.
Regression checks compare full parsed DOM against fragment assembly for both
renderers, nested and flat trees, changed ordering/selection, focus, and actions.
This reduced refresh work but did not resolve all 50 ms typing misses.
