# Publish a confirmed new workspace to the tab catalog before navigation

Workspace creation refreshes `workspacesList`, but tab rendering reads the separate
`workspaceTabsAll`. Without adding the confirmed created row to that collection,
the dashboard opens while its tab waits for the five-second catalog poll. Native
creation measurements exposed 4.4–4.7 seconds despite 70–100 ms creation requests.

After the authoritative post-create catalog returns, append the created row only
if its absolute path is absent, then navigate normally. Preserve all existing tab
objects, pending open/close state and ordering; do not replace the whole collection
with the snapshot. Keep the captured vault, pending-catalog wait, failure behavior,
missing-row fallback and duplicate prevention. Measure through the new active tab
and dashboard, not just the POST response or closed modal.
