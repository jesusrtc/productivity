# Lab migrations and expected formats

This is documentation for agents working with existing Lab data. These commands
read packaged guides; they do not inspect, modify or migrate the client's files.

```bash
lab migrations
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

```text
tasks/<id>.md                  Tasks and subtasks
notes/<id>.md                  Notes, threads, meetings, series, derived documents
projects/<id>.md               Independent projects
.assistant/workspaces.json     Symbolic workspace references
.assistant/manifest.json       Schema version and moved-asset aliases
```

Markdown frontmatter is the source of truth. Schema 2 uses `schema`, `type`,
immutable `id`, `title`, `created`, and `updated`. Tasks add `status` and
`priority`. Tasks/notes may each reference one optional `project`, one optional
`workspace`, and a typed `parent`. A project can span workspaces; changing a
relationship does not move a file. Metadata stays out of the document body.

`lab migrations assistant-records-v2` includes complete examples, legacy-to-new
mapping, preservation rules, and the existing migration/verification commands.

## Other compatibility guides

- `workspace-agent-context`: workspace-owned instructions and the existing
  commands for inspecting or removing recognized legacy Lab symlinks.
- `vault-workspace-names`: current terminology and legacy path compatibility.
  New terminology alone is not a reason to rename a directory.

`lab agent context migrations`, `lab agents context migrations`, and
`lab context migrations` read this same overview. The context supplied when an
agent starts, and the “Lab agent context” document in the UI, point to this guide.
Starting an agent does not run a migration.
