# Assistant

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
