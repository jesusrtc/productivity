# Assistant tasks are independent of project/workspace storage

On September 15, 2026 the user requested a data-model redesign:

- Each task may have one project and one symbolic workspace association. A
  project may span workspaces, and a workspace may contain multiple projects.
- The workspace is a convenient view of associated work, not a required place
  to execute the task or a physical owner of its file.
- Tasks and notes should live in their own top-level folders, with optional
  projects and robust references. The task document rail should become nested
  tabs/subtabs like Google Docs, supporting subtasks or threads.

Schema 2 is implemented, and the client database was migrated with a verified
backup on September 15, 2026. See `docs/assistant-independent-records.md`.

- Flat `tasks/`, `notes/`, and `projects/` folders; subtasks are tasks with typed
  `parent` references. Meetings/series/questions/documents are note types.
- Stable IDs, per-record legacy aliases and relative-resource bases; original
  bodies preserved byte-for-byte. Optional projects start empty, never inferred
  from a legacy workspace folder or group label.
- `.assistant/workspaces.json` stores symbolic workspace references and context.
  `.assistant/manifest.json` records the format and relocated asset aliases.
- `lab assistant migrate` defaults to a dry run; `--apply` stages and verifies
  records, backs up the original tree, switches with a maintenance marker, and
  rolls back on errors. `lab assistant verify` checks relationships and IDs.
- CLI/API support independent project/workspace changes and note creation.
  Modal tabs show nested tasks and notes. Empty collection folders remain visible
  in the Assistant file explorer. Markdown remains the source of truth.
- The optional SQLite cache, drag ordering, and dedicated workspace task panel
  remain extensions; do not claim those are implemented.
