# Lab migrations and expected formats

This is documentation for agents working with existing Lab data. These commands
read packaged guides; they do not inspect, modify or migrate the client's files.

```bash
lab migrations
lab migrations assistant-document-tasks
lab migrations assistant-documents
lab migrations assistant-subtabs
lab migrations assistant-records-v2
lab migrations workspace-agent-context
lab migrations vault-workspace-names
```

Read the applicable guide after a Lab update or when older instructions no
longer match the data layout. Read the target's AGENTS.md and README.md, inspect
the current format, and follow the user's authorized scope before changing it.
Keep existing IDs, user content, unknown fields and references. Do not infer
business projects or workspace mappings from similar folder names.

## Assistant: expected layout

`documents/<id>.md` contains one independent task/note plus
all nested subtabs. `projects/<id>.md` holds independent business projects.
Subtab metadata lives in the containing file's frontmatter `tabs` array; stable
body markers identify each subtab. Typed parent references build the tree.
Subtabs inherit the root task/note's optional project and symbolic workspace.

Markdown is authoritative. `.assistant/index.json` caches metadata, summaries,
references and calculated status; Lab refreshes it after writes and detects
external Markdown edits on reads. Never edit that generated file.

The manifest's `document_format: "embedded-subtabs-v1"` distinguishes this from
older separate-record schema 2. `lab migrations assistant-subtabs` gives the
exact format, aggregate status rules, preservation requirements and existing
conversion commands. `lab migrations assistant-records-v2` documents the older
flat-record migration as an intermediate step for workspace-folder databases.

After `lab assistant migrate --documents --apply`, the manifest also records
`storage_layout: "unified-documents-v1"`. Existing clients retain tasks/notes
until explicitly migrated. Read `lab migrations assistant-documents` for the
per-client sequence, verified backup/rollback, old-link compatibility and the
optional `external_url` property. Restart the updated backend after migration.

Document-owned tasks: `lab migrations assistant-document-tasks` describes the
explicit migration from tracked tabs and Markdown checklists into each document’s
JSON tasks array, preserving content tabs, stars, and saved dashboard sections.

The manifest marker `task_format: "document-tasks-v1"` identifies a migrated
database. Without it, the existing tracked-tab model remains active. Updating
Lab alone does not migrate client data.

## Other compatibility guides

- `workspace-agent-context`: workspace-owned instructions and the existing
  commands for inspecting or removing recognized legacy Lab symlinks.
- `vault-workspace-names`: current terminology and legacy path compatibility.
  New terminology alone is not a reason to rename a directory.

`lab agent context migrations`, `lab agents context migrations`, and
`lab context migrations` read this same overview. The context supplied when an
agent starts, and the “Lab agent context” document in the UI, point to this guide.
Starting an agent does not run a migration.
