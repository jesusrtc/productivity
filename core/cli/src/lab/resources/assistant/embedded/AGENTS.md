# Assistant database · embedded subtabs

This is the client-owned global task/note database, independent of Lab workspaces.

The client alone decides the content, structure, headings, language, and
formatting of tasks, notes, and their tabs. Lab supplies storage, metadata,
tab relationships, and rendering. New document bodies are empty; do not
add templates, required sections, or writing conventions unless the client
requests them. The serialization contract below is technical, not a content
template. Preserve existing client content and instructions.

## Start each session

1. Read this file and README.md.
2. Run `lab assistant ls --status open` before creating duplicate work.
3. Read `lab migrations assistant-subtabs` for the exact Markdown format.
4. Use `lab assistant workspace ls` and `lab assistant project ls` to resolve
   existing references. Match exact workspace paths; never guess a project from
   a workspace or group label.
5. Keep source code and generated project assets in the owning repository;
   store references and task/note context here.

## Storage

One `tasks/<id>.md` per independent task; one `notes/<id>.md` per independent
note. Every subtab, including nested subtabs, lives inside that same Markdown
file. Optional independent projects live at `projects/<id>.md`.

The manifest uses schema 2 and `document_format: "embedded-subtabs-v1"`.
Markdown frontmatter is authoritative. Root metadata uses schema, type,
immutable id, title, created, updated, optional project and workspace, and
parent null. Each task has status and priority. Each subtab has metadata in the
frontmatter's single-line JSON `tabs` array, plus its Markdown body between
`<!-- lab:subtab ID -->` and `<!-- /lab:subtab ID -->` markers. The exact newline
contract and a complete example are in `lab migrations assistant-subtabs`.

Subtabs replace both threads and subtasks as the user-facing concept. Their
stable typed parent IDs build a tree within the document; position orders
siblings. New subtabs are note_type subtab. Migrated task-type children keep
their original IDs/types for compatibility. Never split them back into files.

A root task/note may reference one project and one symbolic workspace.
Subtabs inherit both. Projects may span workspaces; a workspace may contain
several projects. Relationship changes never move files. Preserve aliases,
legacy_path, legacy_metadata, unknown metadata, and all unrelated content.

`.assistant/index.json` is a generated metadata/search cache, not an editable
source. Lab updates it after metadata writes and checks for direct Markdown
edits on reads/refresh. `lab assistant verify` refreshes and validates it.
Keep `.assistant/workspaces.json` references and immutable raw originals in
`.assistant/assets/`; do not hand-edit generated registries or indexes.

## Commands

```text
lab assistant path
lab assistant verify
lab assistant workspace ls
lab assistant project ls
lab assistant project add <id> --name <name>
lab assistant add "Task title" [--project <id>] [--workspace <id>] [--priority P1]
lab assistant ls --status open [--project <id>] [--workspace <id>]
lab assistant show <id>
lab assistant set <id> <field> <value>
lab assistant done <id>
lab assistant note add "Note title" [--project <id>] [--workspace <id>]
lab assistant note ls
lab assistant note show <id>
lab assistant note set <id> <field> <value>
lab assistant subtab add "Subtab title" --parent <id> --parent-type task|note
lab assistant subtab ls --parent <id> --parent-type task|note
lab assistant subtab show <id>
lab assistant subtab set <id> status not_started|in_progress|done|skipped
lab assistant subtab set <id> due YYYY-MM-DD
lab assistant subtab set <id> priority P0|P1|P2|P3
lab assistant subtab set <id> owner "POC name"
lab assistant meeting add "Meeting title" --workspace <id> [--date YYYY-MM-DD]
lab assistant meeting ls
lab assistant meeting show <id>
```

Use null to clear optional values. Prefer commands for metadata validation;
direct Markdown edits are supported. Re-read the latest file before a targeted
edit, preserve siblings, and verify structural changes. Agents editing different
subtabs are editing the same file. IDs and `created` never change on an edit.

## Progress and content

Leaf status: not_started, in_progress, done (Completed), skipped. Overall status
is derived recursively: none started → Not started; some started/completed/
skipped → In progress; all done/skipped → Completed. Skipped completes a whole
branch without deleting it. Overall cancellation is manual (`status cancelled`).
Legacy inbox/ready mean Not started; waiting/blocked/ready_to_review count as
In progress. Reopening a child recomputes the overall status. Do not maintain
another copy of the calculated overall status. Explicit leaf completion also
checks unchecked Markdown items if the client has used them.

`tldr` is a concise description; `owner` is POC; due is the actual deadline;
priority is P0 urgent, P1 important, P2 normal, P3 someday. Recurrence is null
(once), weekly, monthly or yearly. `lab assistant repeat <id>` explicitly creates
the next occurrence after completion. Waiting/review context fields remain
supported. Any client-authored H1–H6 heading supports right-click → Copy content
for Google Docs-compatible rich text. No heading is required.

One tab opens directly; multiple tabs get a generated Index with the clickable
tree, description, status, due, priority and POC. Do not save Index as another
file. Raw captured notes remain immutable.

The document rail's + adds a tab at the same level as the main tab, inside the
same file. Add subtab in a row menu nests a child. Top-level tab metadata uses
`top_level: true` and a parent reference to the document root; existing children
retain their nesting. CLI equivalent: `lab assistant subtab add "Title" --parent
<root-id> --parent-type task|note --top-level` (one command line).

## Unified document storage and external links

Read `lab migrations assistant-documents` for the current storage contract and
per-client migration steps. After `lab assistant migrate --documents --apply`,
all independent tasks/notes/meetings/series live in `documents/<id>.md`; projects
remain in projects/. Without `storage_layout: "unified-documents-v1"`, the
older tasks/notes paths above still apply. Never move files or edit the generated
manifest/index manually. Preserve IDs, embedded subtabs, content and aliases.
Migration does not rewrite existing client instructions; update obsolete
technical path references while preserving client-authored writing rules.

Optional `external_url` on a document or tab is an absolute HTTP(S) URL or null.
Set it in **External document URL** in the header or with
`lab assistant document set <id> external_url '<url>'`. The **External doc**
button opens the linked document in the clicking client's browser.
