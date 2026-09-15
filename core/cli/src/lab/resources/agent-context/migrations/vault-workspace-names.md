# vault-workspace-names · Current Lab terminology

- Vault: a registered storage root.
- Workspace: a persistent work area inside a vault.
- Terminal: a shell or agent terminal; tabs are navigation and sessions are runtime state.
- Assistant project: an independent task grouping, not a synonym for a workspace.

Use `lab vault --help`, `lab workspace --help`, and `lab terminal --help` for
current commands. LAB_VAULT selects a vault; LAB_WORKSPACE remains a legacy
compatibility input. Use canonical names for new configuration and code.

Existing legacy directory paths, registry files and metadata are read through
explicit compatibility adapters. Do not rename directories merely to match
new UI terminology: active terminals, worktrees and notebook kernels may refer
to those exact paths. A physical workspace rename is a separate explicit task.

There is no automatic filesystem conversion for this terminology guide. For
Assistant's independent records use `lab migrations assistant-records-v2`.
