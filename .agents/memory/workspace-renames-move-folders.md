# Workspace rename moves its folder and preserves session UUIDs

The user explicitly wants renaming to move the physical workspace directory to
the slug of the new display name. Display-only aliasing is insufficient. Both
context-menu entry points use POST /api/workspaces/{id}/rename, backed by
`lab workspace rename <id> <name>`.

Keep the internal workspace ID fixed and resolve it through the rebuildable
vault-local workspace-locations index. Terminals use independent UUIDs in a
durable session index and the saved workspace session list. New tmux names are
`neurona-<uuidhex>`; legacy live sessions retain their names and sockets until
recreated. Labels, agent resume IDs, and browser terminal connections survive.

Move Lab-owned paths and browser tab state, repair nested Git worktree backlinks,
reject destination collisions, and prevent moves during active notebook writes
or terminal mutations. Idle notebook kernels retain their canonical session key.
Do not edit user scripts or arbitrary process state to replace old absolute paths.
