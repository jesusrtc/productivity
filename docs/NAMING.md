# Vaults, workspaces, and terminals

Lab uses three distinct names:

| Entity | Meaning | Example |
| --- | --- | --- |
| Vault | A named storage root containing workspaces, shared files, and settings. | Local or SSD |
| Workspace | A persistent work area with its files, repositories, notebooks, and terminals. | Example workspace |
| Terminal | A terminal running Codex, Claude, Copilot, or a shell. | Codex |

A **tab** is a navigation control, not another storage entity. Closing a workspace tab does not delete its workspace. A terminal **session** describes the running process or resumable conversation. Home and Assistant are app-wide destinations. Assistant organizes tasks by workspace and task group; its database is independent of the vaults.

## Public commands and configuration

```sh
lab init ~/work/my-vault
lab vault list
lab vault use ~/work/my-vault
lab vault current
lab workspace new example
lab workspace set example name "Example workspace"
lab task ls --workspace example
```

`LAB_VAULT` selects the storage root. Its registry is `~/.lab/vaults.toml`, with `[[vaults]]` entries. A newly initialized vault has a `[vault]` section in `lab.toml`, a `workspaces/` directory, and optional shared `vault.json` configuration. Each work area has `workspaces/<id>/workspace.json`. Shared configuration uses `workspace` for the settings inherited by those work areas.

HTTP contracts use `/api/vaults`, `/api/vault/...`, and `/api/workspaces/...`. The `vault` request field selects the storage root; `workspace_id` identifies the work area. Browser links use `?workspace=<absolute-path>&vault=<vault-id>`. Identifiers, modules, DOM IDs, CSS classes, tests, and examples follow the same distinction.

## Existing installations

This release replaces the old root-level “workspace” terminology with “vault,” and the old work-area “project” terminology with “workspace.” Update scripts to the new CLI and API names; the old `lab workspace` command now manages work areas.

Compatibility is confined to readers and migration code:

- The old registry and `LAB_WORKSPACE` remain readable. `LAB_VAULT` takes precedence, and registry writes use the new filename and fields.
- Existing `projects/` directories and their metadata remain usable at their original paths. New vaults use `workspaces/`. Keeping existing absolute paths preserves notebook kernel identity, linked files, Git worktrees, and running terminal working directories.
- Old shared configuration is normalized on read. Editing it writes `vault.json`, preserving the old source file.
- Saved account grants, terminal ownership, Assistant mappings, browser preferences, and bookmarked work-area links retain their meaning.
- Provider-owned formats such as Claude's `.claude/projects` and Copilot's `workspace.yaml`, and packaging formats such as `pyproject.toml`, keep their external names.

No user-authored titles, workspace IDs, paths, command strings, or conversation text are mechanically renamed.
