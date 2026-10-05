# Workspace-owned Objective files

Each Objective lives inside its workspace, in
`objectives/<folder>/.objective.json`. Lab discovers these files directly;
the folder name does not have to match the Objective's stable `id`.
The manifest is authoritative for its links, tasks, resources, worktrees and
shared/task/archive associations. Editing a manifest outside Lab is supported.
Lab detects these changes on subsequent reads and rejects stale UI writes.

Minimal format:

```json
{
  "version": 1,
  "id": "phone-recovery",
  "name": "Phone recovery",
  "purpose": "Restore reliable verification",
  "resources": [
    {"id": "notes", "kind": "document", "title": "Notes.md", "path": "Notes.md"},
    {"id": "discussion", "kind": "link", "title": "Discussion", "url": "https://example.com"}
  ],
  "worktrees": [],
  "tasks": [],
  "shared_assets": [],
  "archived_assets": [],
  "asset_shelf": []
}
```

Owned `document` and `notebook` paths are relative to the containing Objective
folder. The Markdown/notebook files live there too. Links are manifest entries;
they do not need individual files. Optional link fields include `tldr`,
`metadata`, service/custom icons and nested `sublinks` with stable IDs.
Existing `kind: "file"` resources retain their source `file_root` and relative
`path`. Assistant references retain their original `assistant_root`,
`document_id` and optional `tab_id`; never copy or migrate Assistant ownership.
Worktrees retain their existing paths and IDs.

Task entries retain their `id`, `title`, `done`, `due`, `document_id`, `tab_id`,
`children`, `assets` and optional `icon_asset_id`. Asset references preserve
`resource_id`, exact `tab_id` / `sub_link_id`, or a folder's `root` and `path`.
Keep every existing ID, reference and unknown field when adapting a file.
Unregistered explorer files are not automatically imported as assets.

Tasks can also have `status`: `todo` (Undo), `in_progress` or `done` (Completed).
When present, it determines the compatibility `done` boolean; keep both aligned
when editing a manifest. Existing tasks without `status` retain their `done`
behavior. A `task-update` action accepts either `status` or the existing `done`
boolean. Completed/Undo also update subtasks; In progress preserves their states.

`.lab/objectives-state.json` contains only workspace UI/runtime state:
five focused IDs, ordering IDs, enabled state and terminal associations. It is
not an Objective catalog. Colors are calculated from the focus-slot position.
Use `lab objective apply --workspace <id> --file <action.json>` for UI mutations;
do not hand-edit workspace.json, tasks.json or generated indexes.

## Converting the previous registry

Read the target workspace's instructions and inspect its current content first.
Preview with:

```bash
lab objective migrate --workspace <id>
```

Within the user's authorized scope, convert with:

```bash
lab objective migrate --workspace <id> --apply
```

The converter preflights every target, refuses conflicting/invalid files,
preserves a byte-identical `.lab/objectives.legacy.json` backup (using a numbered
name if necessary), writes one manifest per Objective, then publishes the new
layout and removes the old `.lab/objectives.json` source. It never changes
Markdown, notebooks, Assistant content or terminal launch metadata.
Interrupted conversions can be retried; identical existing manifests are kept.
Repeating a completed conversion makes no changes.

Old registries remain readable without modification. The first successful
Objective mutation also converts that workspace. Invalid actions and ordinary
reads do not migrate it. Updating Lab or launching an agent does not itself
convert workspace data. Once converted, removing a manifest removes it from
discovery; legacy backups never restore removed Objectives automatically.

Back up the complete workspace before manually rolling back. Stop Objective
writes, restore the legacy backup as `.lab/objectives.json`, and remove the
converted manifests and `.lab/objectives-state.json` only after confirming
they contain no newer edits. Preserve all Markdown/notebook files.
