# Assistant schema 2: format and migration instructions

Current storage: read `lab migrations assistant-documents` to consolidate
independent tasks and notes in `documents/`. The format and legacy path examples
below remain valid for clients that have not yet run that migration.

Scope: the client-global Assistant database selected by LAB_ASSISTANT_HOME.
Workspace-local tasks.json files use a different contract. Read the target's
AGENTS.md and README.md, then inspect its manifest before editing.

This is the intermediate separate-record format. If the manifest already has
`document_format: "embedded-subtabs-v1"`, use `lab migrations assistant-subtabs`
instead; never recreate separate child files in that format.

## Expected files

```text
tasks/<id>.md                   Tasks and subtasks, one flat collection
notes/<id>.md                   All note types, one flat collection
projects/<id>.md                Independent business projects
.assistant/workspaces.json      Symbolic workspace references and context
.assistant/manifest.json        {"schema": 2, "state": "active", ...}
.assistant/assets/<id>/raw.txt  Original captured notes, when present
```

Use one frontmatter field per line with JSON-compatible values. The filename
must match the immutable id. Ordinary Markdown follows the closing delimiter.

### Task or subtask

```markdown
---
schema: 2
type: "task"
id: "task_example"
title: "Prepare review"
created: "2026-09-15T10:00:00Z"
updated: "2026-09-15T10:00:00Z"
status: "ready"
priority: "P2"
project: "launch"
workspace: "demo"
parent: null
position: 0
due: null
recurrence: null
---
# Context

Review the deliverable.

# Next actions

Record the outcome here.
```

The project and workspace IDs above must already exist. Use null when unassigned.
A subtask also lives in tasks/ and references its parent, for example:
`parent: {"type":"task","id":"task_example"}`.

Statuses: inbox, ready, in_progress, waiting, blocked, ready_to_review, done.
Priorities: P0–P3. Optional recurrence: null (once), weekly, monthly, yearly.
`due` is a deadline, `scheduled` is a planned work date, and `defer_until` defers
visibility; dates use YYYY-MM-DD. Complete descendant tasks and checkboxes before
completing a parent. Set completed when status becomes done.

### Note or thread

```markdown
---
schema: 2
type: "note"
id: "note_example"
title: "Review discussion"
created: "2026-09-15T10:00:00Z"
updated: "2026-09-15T10:00:00Z"
note_type: "thread"
project: null
workspace: null
parent: {"type":"task","id":"task_example"}
position: 0
---
# Notes

Discussion and decisions.
```

Note types: plain, thread, meeting, series, question, document. A meeting may
reference a series note ID with `series`. Questions and derived documents can
reference a meeting with `parent: {"type":"note","id":"meeting-id"}`.
Original raw.txt is immutable; edited or derived content gets its own note.

### Project and workspace references

A project file uses schema 2, type "project", id, title, status "active",
created, updated, and a Markdown body. It is independent of a Lab workspace.
The workspace registry is a JSON object with schema 2 and a workspaces array;
each reference retains its id, name, vault, vault_path and absolute workspace_path.
Use `lab assistant workspace ls` to inspect existing mappings and
`lab assistant project ls` to inspect independent projects.

A task/note can have one optional project and one optional workspace. The same
project may span workspaces; a workspace may contain tasks from several projects.
`parent` is null or a typed task/note reference. Avoid cycles and missing IDs.
`position` orders sibling tabs. Children retain their own project/workspace values.

## Mapping older data

| Legacy location | Schema 2 destination |
| --- | --- |
| workspaces/<workspace>/tasks/<id>.md | tasks/<id>.md |
| workspaces/<workspace>/subtasks/<id>.md | tasks/<id>.md with a typed parent |
| workspaces/<workspace>/meetings/<id>.md | notes/<id>.md, note_type meeting |
| workspaces/<workspace>/meeting-series/<id>.md | notes/<id>.md, note_type series |
| A meeting's questions/ or documents/ | notes/<id>.md with a meeting parent |
| workspace.md or legacy project.md mapping | .assistant/workspaces.json |

Some older databases use projects/ where the table says workspaces/.
Preserve those exact workspace associations. Start independent projects empty;
do not turn the old workspace folders or group labels into business projects.

Keep IDs, Markdown bodies, unknown metadata, note originals, and relationships.
`aliases` stores old relative document paths; `legacy_path` keeps the base for
old relative links; `legacy_metadata` is provenance, not active metadata.
New references should use canonical paths. Record assets moved by the migration
in manifest asset_aliases. Keep project-owned assets in their owning repository.

## Existing tools for an authorized migration

This guide does not execute these commands. When conversion is the user's task:

```bash
lab assistant path
lab assistant migrate --dry-run
lab assistant migrate --apply
lab assistant verify
```

The existing migrator stages and validates records, copies originals to
.assistant/backups/<run-id>/, checks hashes, and records its journal under
.assistant/migrations/<run-id>/journal.json. It preserves IDs and exact bodies,
updates the database's AGENTS.md/README.md, and returns the backup/journal paths.
An already-migrated database is verified without another conversion.

Ordinary cutover errors restore the original layout. If the process was killed
and the manifest still says migrating, inspect the running process and journal;
preserve current files and any newer edits before manual recovery. Do not clear
the marker blindly or replace newer edits with a backup. There is no automatic
recovery command for an abrupt process death.

Install a compatible reader and restart a running Lab backend before converting.
Afterward verify records and relationships, read the updated local contract,
and refresh the UI. Neither this documentation command nor agent startup changes
client files.
