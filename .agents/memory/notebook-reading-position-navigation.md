# Notebook reading position uses stable cell IDs

Large notebook views persist the last-read cell in browser-local storage,
scoped by owning workspace and notebook path. Restore by stable nbformat cell
ID first and use the prior index only as a fallback, so insertions do not move
the bookmark to unrelated content. A currently running cell takes priority on
open. Keep the Start/current/End controls in an upper sticky strip clear of the
terminal panel. Persist the path-scoped output-only toggle too: hide committed
code source and outputless code cells, while leaving markdown, outputs, drafts,
and running cells visible.
