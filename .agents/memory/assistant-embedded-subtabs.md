# Assistant: one Markdown per task/note with embedded subtabs

The user's September 15, 2026 revision supersedes the separate-child-file part
of assistant-independent-projects-and-workspaces.md. One task/note file contains
all nested subtabs and their metadata; subtask and thread are one UI concept.

- Manifest schema remains 2; document_format is embedded-subtabs-v1.
- Frontmatter tabs is a JSON array; stable body markers delimit each subtab.
  IDs and typed parents build the tree. The containing root owns the optional
  project/workspace associations, inherited by subtabs.
- .assistant/index.json is a generated, rebuildable metadata/search cache.
  Metadata writes refresh it, and readers detect direct Markdown edits.
- More than one tab adds a virtual Index: clickable tree, one-line description,
  status, due, priority and POC (owner). A single tab opens directly.
- Overall: none started = not_started; any started/done/skipped = in_progress;
  all done/skipped = done. Skipped completes its branch. Cancelled is manual on
  the root. Child reopening recalculates ancestors; don't persist derived status
  as a second editable copy. Preserve legacy lifecycle context.
- Minimal neutral UI, compact top metadata, comfortable copy targets. Tab
  changes preserve outgoing content during fetch, pane DOM and scroll. Identical
  polling responses don't rebuild the list or shared shell.
- lab migrations assistant-subtabs and lab agent context tasks/migrations
  explain the format. lab migrations remains read-only documentation.
- The live database conversion retained 41 records in 25 Markdown documents,
  with 16 subtabs, verified backup/aliases/bodies. Use the existing --embedded
  migration option only for authorized old-format databases.
