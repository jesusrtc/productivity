# Batch terminal ownership per vault

When reconciling a tmux listing, resolve unknown UUID names with
`workspace_identity.session_owners(root, names)` once per vault. Repeating
`session_owner` for every foreign session walks the same workspace files
again and again. The measured Home listing made 108 lookups and 540 pseudo
workspace metadata resolutions; batching reduced reconciliation from about
70 ms to 3–6 ms with the same live sessions.

Keep index precedence, recovery from durable workspace/pseudo-workspace
session UUIDs, and fresh reads on the next request. Unknown UUID names
cannot match legacy names, but actual legacy names must still pass through
the existing parser. A failed tmux listing must never prune the registry.
