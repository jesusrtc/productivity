# Assistant

The client alone decides the content, structure, headings, language, and
formatting of tasks, notes, and their tabs. Lab supplies storage, metadata,
tab relationships, and rendering. New document bodies are empty; do not
add templates, required sections, or writing conventions unless the client
requests them. The serialization contract below is technical, not a content
template. Preserve existing client content and instructions.

One Markdown file per independent task or note, containing all its subtabs.

```text
tasks/<id>.md              Task metadata, main content and all subtabs
notes/<id>.md              Note metadata, main content and all subtabs
projects/<id>.md           Optional projects, independent of workspaces
.assistant/
  manifest.json           Schema 2 + embedded-subtabs-v1 document format
  index.json              Rebuildable metadata/search cache
  workspaces.json         Symbolic workspace references
  assets/                 Immutable raw notes and referenced resources
  backups/                Verified migration backups
  migrations/             Migration journals
```

The Markdown is authoritative. Subtab metadata lives in its frontmatter's
`tabs` array; body markers identify each subtab by stable ID. Nested `parent`
references and sibling `position` build the document tree. Subtabs inherit the
containing task/note's one optional project and one optional workspace.
Projects can span workspaces. Changing associations never moves a document.

Lab maintains the JSON index after its writes and detects direct file edits on
the next read/refresh. It can rebuild a deleted index. Do not edit it manually.
Use `lab assistant verify` to refresh it and validate the complete graph.

With subtabs, a generated Index shows their tree, summary, status, due, priority
and POC. Clicking a row opens that tab. Progress rolls up automatically; skipped
branches count as completed, and overall cancellation is manual. With only one
tab, Lab opens its content directly. Properties stay in the compact top bar.

Read AGENTS.md and `lab migrations assistant-subtabs` for the exact format and
commands. `lab agent context tasks` and `lab agent context migrations` point to
the same contract. Legacy IDs, links, original bodies and backups are retained.
The database is selected by LAB_ASSISTANT_HOME; `.lab/` holds runtime state.

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
