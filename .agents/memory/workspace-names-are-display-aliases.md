# Workspace names are display aliases

Workspace directory names and `workspace.json.id` are stable technical identifiers.
They continue to drive URLs, terminal ownership, config lookup, and API calls.

`workspace.json.name` is the editable human-facing label. The UI exposes it as
`display_name` while keeping the existing `name` field in workspace-list API rows
equal to the stable id for backward compatibility. Workspace rename controls must
write through `lab workspace set <id> name <value>` and must target the owning
vault without changing the globally active vault.

The active tab must also reconcile the authoritative `workspace-info` name into
its catalog/tab caches. Catalog polling can finish out of order after a rename;
while active, the workspace detail name wins so the folder id cannot flash back.
