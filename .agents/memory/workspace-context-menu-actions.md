# Workspace context menus offer rename and delete

Right-clicking either a workspace row in its vault or its top-level tab opens
the same menu, with Rename workspace and Delete workspace. This supersedes the
earlier vault-list-only deletion entry point.

Rename reuses the single-name workspace form, captures the owning vault and
stable workspace ID/path, and calls the dedicated rename API. Rename now also
moves the folder; see workspace-renames-move-folders.md for identity and path rules.

Delete opens transient delete mode beside Focus for the exact selected workspace.
The final confirmation names the folder and permanent data loss. Normal navigation
and reload clear delete mode. The API verifies the vault/path and stops workspace
resources before deleting through `lab workspace rm`.
