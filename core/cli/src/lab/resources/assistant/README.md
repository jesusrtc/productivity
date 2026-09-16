# Assistant

The client alone decides the content, structure, headings, language, and
formatting of tasks, notes, and their tabs. Lab supplies storage, metadata,
tab relationships, and rendering. New document bodies are empty; do not
add templates, required sections, or writing conventions unless the client
requests them. The serialization contract below is technical, not a content
template. Preserve existing client content and instructions.

One global collection of independent tasks, notes, and projects.

```text
tasks/                   Tasks and subtasks, one Markdown file per ID
notes/                   Notes, threads, meetings, questions, series
projects/                Independent projects, one Markdown file per ID
.assistant/
  workspaces.json        Optional symbolic workspace references
  manifest.json          Schema version and moved-asset aliases
  assets/                Original notes and Assistant-owned resources
  backups/               Verified migration backups
  migrations/            Migration journal and original tree
```

A task or note can belong to one project and one workspace, independently.
Projects can span workspaces; workspaces can contain work from many projects.
Moving those relationships does not move the document. Parent references build
nested tabs without nesting files. Project records start empty until created;
legacy workspace folders are not automatically treated as business projects.

Markdown frontmatter is the source of truth. Identity, references, dates and
status stay in metadata; the body stays ordinary readable Markdown. The UI
keeps editable properties in the top bar. There is no required separate index
or duplicate JSON copy of each record.

Read `AGENTS.md` for the command and lifecycle contract. Use
`lab assistant verify` to check identities and relationships.

The database is selected by `LAB_ASSISTANT_HOME` in the Lab client `.env`.
`.lab/` contains terminal/runtime state. Legacy links are resolved through
record aliases; migration copies are retained under `.assistant/`.
