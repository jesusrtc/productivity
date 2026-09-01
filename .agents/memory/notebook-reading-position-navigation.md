# Notebook reading position uses stable cell IDs

Large notebook views persist the last-read cell in browser-local storage,
scoped by owning workspace and notebook path. Restore by stable nbformat cell
ID first and use the prior index only as a fallback, so insertions do not move
the bookmark to unrelated content. A currently running cell takes priority on
open. Keep the floating Start/current/End controls clear of the terminal panel.
