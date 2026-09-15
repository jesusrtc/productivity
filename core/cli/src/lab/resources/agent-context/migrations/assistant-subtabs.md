# Assistant: one Markdown document with embedded subtabs

Current document format: `embedded-subtabs-v1`, stored in the schema-2 manifest
as `document_format`. Read the database AGENTS.md, README.md, and manifest first.
`lab migrations assistant-subtabs` prints this guide; it never changes data.

## Files and authority

- `tasks/<id>.md`: one independent task, including every nested subtab.
- `notes/<id>.md`: one independent note, including every nested subtab.
- `projects/<id>.md`: optional independent business projects.
- `.assistant/workspaces.json`: symbolic workspace references.
- `.assistant/index.json`: generated metadata/search index, safe to rebuild.
- `.assistant/manifest.json`: schema, document format, compatibility asset aliases.
- `.assistant/assets/`: immutable captured originals and referenced resources.

Markdown is the source of truth. Do not edit index.json or store another
editable copy of metadata there. Lab rebuilds the index after its own metadata
writes and checks document fingerprints on every read/refresh, so direct agent
edits are picked up on the next read. `lab assistant verify` also refreshes it.
The index contains IDs, paths, aliases, metadata, summaries, and derived status.
Bodies remain in Markdown. A deleted or stale index can be regenerated.

A task or note has one optional project and one optional workspace, independent
of each other. Projects may span workspaces. The workspace is a convenient
filter, not physical ownership. Subtabs inherit those two links from their
containing document. Subtabs are one concept: do not create separate thread and
subtask representations for the same work.

## Exact Markdown format

Use one frontmatter field per line; values must be JSON-compatible. `tabs` is a
JSON array on one frontmatter line. Root ID and filename match. Subtab IDs are
stable, unique across the database, and independent of their title or position.
All subtab metadata lives in that array; do not add nested frontmatter blocks.

```markdown
---
schema: 2
type: "task"
id: "task_review"
title: "Prepare review"
created: "2026-09-15T10:00:00Z"
updated: "2026-09-15T10:00:00Z"
status: "not_started"
priority: "P2"
project: null
workspace: null
parent: null
tabs: [{"schema":2,"type":"note","id":"note_research","note_type":"subtab","title":"Research","parent":{"type":"task","id":"task_review"},"position":0,"status":"in_progress","priority":"P1","due":"2026-09-30","owner":"Jesus","tldr":"Collect the supporting facts.","created":"2026-09-15T10:00:00Z","updated":"2026-09-15T10:00:00Z"}]
---
# Context

The main tab's content.

<!-- lab:subtab note_research -->
# Research

The subtab's content.

<!-- /lab:subtab note_research -->
```

A body segment begins with a newline, its opening marker and a newline; it ends
with a newline, its closing marker and a newline. Keep each pair intact and
unique. These marker lines are reserved; do not use them inside content/code
examples in an actual subtab. Keep content inside the matching markers and all
main content before the first marker. The parser preserves body text exactly.

For nested subtabs, set `parent` to the containing subtab's typed ID. All
parents must belong to this same Markdown file, with no cycles. `position`
orders siblings. Body segments remain flat in the file; their parent metadata
builds the tree. Migrated task-type children keep their IDs and `type: task` for
link compatibility, but the UI treats them as subtabs too.

Canonical references are `tasks/<root-id>.md#tab=<subtab-id>` (or notes/).
This is a document reference, not a second filesystem path. In URLs, encode it
as the `task` or `note` query parameter. Old IDs and paths remain aliases.
Preserve aliases, legacy_path (relative asset base), legacy_metadata and unknown
fields. Never regenerate IDs when renaming or reordering tabs.

## Progress

Leaf statuses: `not_started`, `in_progress`, `done` (Completed), `skipped`.
The overall task/note can be explicitly `cancelled`; subtabs use `skipped`.
Parents derive status from direct child branches recursively:

- All children done or skipped → Completed.
- At least one child started, done or skipped, with work remaining → In progress.
- None started → Not started.
- Manual cancellation overrides the overall result until resumed.

Skipping a branch counts that branch as complete; its child content and statuses
are retained. Resume a skipped branch by setting its status to its computed
child status. Reopening a completed leaf recomputes every ancestor automatically.
Do not write a second overall status in the index. A stored status on a parent
is only authoritative for explicit cancelled/skipped overrides. Legacy inbox
and ready map to Not started; waiting, blocked and ready_to_review map to In
progress. Preserve their detail fields as context. The CLI refuses forcing parent completion while child branches remain
incomplete. Explicit leaf completion checks its own unchecked action items;
Index aggregation follows subtab statuses.

One document without subtabs shows its only tab. With subtabs, Lab adds a
virtual Index tab containing the clickable tree, one-line description, status,
due date, priority and POC (`owner`). Index is computed, never another file.
Properties remain editable in the compact top bar, outside the Markdown body.

## Agent edits and commands

```bash
lab assistant ls --status open
lab assistant add "Prepare review" --workspace demo
lab assistant note add "Review notes"
lab assistant subtab add "Research" --parent task_review --parent-type task
lab assistant subtab add "Sources" --parent note_research --parent-type note
lab assistant subtab ls --parent task_review --parent-type task
lab assistant subtab show note_research
lab assistant subtab set note_research status in_progress
lab assistant subtab set note_research due 2026-09-30
lab assistant subtab set note_research owner Jesus
lab assistant set task_review status cancelled
lab assistant verify
```

Agents may edit Markdown and its frontmatter directly, or use these commands.
Re-read the latest containing file before editing; preserve sibling sections.
Concurrent work on different subtabs shares one physical file, so merge targeted
edits instead of overwriting a stale whole-file copy. Update `updated`, preserve
`created`, and verify after structural changes. `tldr` is the one-line summary;
`owner` is POC. Due dates are YYYY-MM-DD; do not invent deadlines.

## Conversion from separate records

Install this reader and restart the backend before applying the conversion.
When migration is authorized:

```bash
lab assistant migrate --embedded --dry-run
lab assistant migrate --embedded --apply
lab assistant verify
```

If the database is still in legacy workspace folders, first run the existing
`lab assistant migrate --dry-run` / `--apply` conversion to schema 2.
The embedded conversion backs up and hashes every source file, combines the
tree under its existing root, preserves exact bodies/IDs/old link aliases,
checks the resulting graph and rebuilds the index. Old child project/workspace
associations that differ are retained as provenance in legacy_metadata; active
relationships belong to the containing task/note. Original raw assets stay put.
An ordinary failure restores original files; repeating a completed migration
verifies the existing format. Backup/journal paths are printed in the result.

If interrupted by process death, inspect the maintenance marker and journal,
preserve newer edits, and recover from the verified backup. Do not blindly clear
`state: migrating` or replace newer content. There is no automatic recovery
command for process death. The read-only `lab migrations` and agent context
commands never perform the conversion.
