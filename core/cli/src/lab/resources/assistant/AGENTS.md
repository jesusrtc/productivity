# Assistant database · schema 2

This is the client-owned global Assistant database, independent of Lab workspaces.

The client alone decides the content, structure, headings, language, and
formatting of tasks, notes, and their tabs. Lab supplies storage, metadata,
tab relationships, and rendering. New document bodies are empty; do not
add templates, required sections, or writing conventions unless the client
requests them. The serialization contract below is technical, not a content
template. Preserve existing client content and instructions.

## Start each session

1. Read this file and `README.md`.
2. Run `lab assistant ls --status open` before creating duplicate work.
3. Use `lab assistant workspace ls` for symbolic workspace references and
   `lab assistant project ls` for independent projects. Match the exact
   workspace path; do not infer a project from a workspace or group label.
4. Keep source code and generated project assets in their owning repository.
   Store references and task/note context here.

## Storage and relationships

- `tasks/<id>.md`: all tasks, including subtasks, in one flat folder.
- `notes/<id>.md`: plain notes, threads, meetings, series, questions, documents.
- `projects/<id>.md`: independent projects that can span workspaces.
- `.assistant/workspaces.json`: symbolic workspace mappings and their context.
- `.assistant/assets/<id>/raw.txt`: immutable original notes when captured.
- `.assistant/manifest.json`: schema and compatibility aliases for moved assets.
- `.assistant/backups/` and `.assistant/migrations/`: migration backup and journal.

Each Markdown record has one frontmatter field per line with JSON-compatible
values. Required identity fields are `schema: 2`, `type`, and immutable `id`.
The filename must match the ID. Preserve unknown metadata and Markdown bodies.
Do not rename records, overwrite originals, or hand-edit generated registries.

A task/note has at most one optional `project` ID and one optional `workspace`
ID. These are independent references; changing either never moves the file.
A workspace is a convenient place to resolve work, not its owner.

`parent` is null or a typed reference, e.g. `{"type":"task","id":"task-id"}`.
Tasks and notes may form nested document tabs. Do not create parent cycles.
`position` controls sibling order. Children retain their own project/workspace;
changing a parent does not silently change its children.

Existing migrated IDs remain valid. `aliases` and `legacy_path` preserve old
links and relative resource resolution. `legacy_metadata` is provenance, not
an active second source of truth. New links should use canonical paths.

## Commands

```text
lab assistant path
lab assistant verify
lab assistant workspace ls
lab assistant workspace add <id> --name <name> --vault <vault-id> --path <absolute-workspace-path>
lab assistant project ls
lab assistant project add <id> --name <name>
lab assistant add "Task title" [--project <id>] [--workspace <id>] [--priority P1] [--due YYYY-MM-DD]
lab assistant ls --status open [--project <id>] [--workspace <id>]
lab assistant show <id>
lab assistant set <id> <field> <value>
lab assistant done <id>
lab assistant subtask add "Child title" --parent <task-id>
lab assistant subtask ls --parent <task-id>
lab assistant subtask set <id> <field> <value>
lab assistant subtask done <id>
lab assistant note add "Note title" [--project <id>] [--workspace <id>]
lab assistant note add "Discussion" --kind thread --parent <id> --parent-type task
lab assistant note ls
lab assistant note show <id>
lab assistant note set <id> <field> <value>
lab assistant meeting add "Meeting title" --workspace <id> [--date YYYY-MM-DD]
lab assistant meeting ls
lab assistant meeting show <id>
```

Use `null` to clear an optional property. Pass a JSON object for a parent.
Commands are optional conveniences; Markdown bodies and metadata may be edited directly. Run `lab assistant verify` after
structural changes.

## Lifecycle and content

Task statuses: `inbox`, `ready`, `in_progress`, `waiting`, `blocked`,
`ready_to_review`, `done`. P0 urgent, P1 important, P2 normal, P3 someday.
Complete descendant tasks and Markdown checkboxes before completing a parent.
No heading is required for blockers or results.

Use `waiting_on`, `waiting_since`, `follow_up_at`, `last_follow_up_at`, and
`follow_up_channel` for waiting work; `reviewer`, `review_requested_at`, and
`executor` for review handoffs. `due` is the deadline; `scheduled` is the planned
work date; `defer_until` defers visibility. `recurrence` is null (once), weekly,
monthly, or yearly. `lab assistant repeat <id>` explicitly creates the next
occurrence after completion; it never silently checks work off.

Client-authored headings support right-click → Copy content. No sections are
required for tasks, notes, or meetings. Original raw captures remain immutable.
