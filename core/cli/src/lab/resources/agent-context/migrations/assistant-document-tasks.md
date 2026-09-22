# Assistant: tasks owned by documents

This guide is read-only. Apply the migration only when the client authorizes it.
Prerequisites are schema 2, `embedded-subtabs-v1`, and `unified-documents-v1`.
Read `assistant-documents` and `assistant-subtabs` first if needed. Existing
clients are not silently migrated.

## Storage and behavior

The manifest and each root document use `task_format: "document-tasks-v1"`.
There is still one `documents/<id>.md` per independent document, and all content
subtabs remain embedded in that file. Existing IDs/types/paths/aliases and tab
parentage are preserved. Tabs have `track_task: false`; old tab lifecycle
metadata remains historical and does not control work.

Each root contains a single-line JSON `tasks` array. For example:

```json
[{"id":"task_call","title":"Call Alex","status":"not_started","done":false,"priority":"P2","parent_id":null,"tab_id":null}]
```

Task `id`s are stable and unique within the document. `parent_id` refers to a
task in the same array. `tab_id` is null, the root ID, or an embedded tab ID.
Null-linked subtasks inherit their task parent's link. Task parentage is
independent of content-tab parentage. Status is not_started, in_progress,
blocked, done, skipped, or cancelled. Parent state and document progress are
derived; `done` is a compatibility value kept consistent with status.

Optional task properties include due, priority, owner, recurrence, planned and
deferred dates, follow-up context, summary, group, and attributes. Document
workspace/project, stars, series, labels and retention stay on documents.
Do not reintroduce tracked tabs. Notes and content subtabs keep their editor,
existing content structure and original raw captures.

## Migration

1. Update the client’s Lab installation from `origin/main` using its normal
   update process. Read this guide on that client with
   `lab migrations assistant-document-tasks`. Resolve the exact database using
   `lab assistant path` and its `LAB_ASSISTANT_HOME`; read its instructions.
   Updating Lab does not itself migrate the database.
2. Save drafts, pause editors and stop its Lab backend before applying.
3. Inspect and execute:

   ```bash
   lab assistant verify
   lab assistant migrate --document-tasks --dry-run
   lab assistant migrate --document-tasks --apply
   lab assistant verify
   lab assistant migrate --document-tasks --dry-run
   ```

4. The plan lists every changed document and counts old tracked records,
   Markdown checkboxes, and existing task-array entries. Each tracked record
   becomes an independent task linked to its original content tab. Tab nesting
   remains unchanged. Markdown checkbox state moves to tasks, retaining task
   nesting and completed state. The original words remain as ordinary bullets;
   fenced code examples and immutable raw assets are left alone. Existing
   prototype task arrays are retained and adopted by the standard model.
5. Original documents, manifest, dashboard configuration and client guides are
   copied to `.assistant/backups/document-tasks-<run>/` with verified SHA-256
   hashes. A journal in `.assistant/migrations/` records the plan and result.
   The migration holds the database lock, compares source bytes before writing,
   verifies the result and rolls back on ordinary errors. A second application
   is a no-op. Dashboard filters, positions, stars and series membership are not
   rewritten.
6. Update only obsolete technical storage/command instructions in the client's
   guides, preserving all client content, language and writing conventions.
7. Start the updated backend and reload. Verify the home dashboard and stars;
   open a root and nested tab; create/edit a task and ordinary subtask; create
   a content tab and subtab; edit notes; reopen the last-selected tab.

If interrupted with a `prepared` journal, keep the backend stopped. Verify each
backup against its recorded hash and inspect current files before restoring.
Restore the affected document files and manifest byte-for-byte from that
journal, preserve any later user edits separately, run `lab assistant verify`,
then restart. Do not clear a migration state flag without examining the journal.

## Commands

```bash
lab assistant task ls <document-id>
lab assistant task add "Call Alex" --document <document-id>
lab assistant task add "Review source" --document <document-id> --tab <tab-id>
lab assistant task add "Check a detail" --document <document-id> --parent <task-id>
lab assistant task set <document-id> <task-id> status in_progress
lab assistant task set <document-id> <task-id> priority P1
lab assistant task set <document-id> <task-id> due 2026-10-01
lab assistant task done <document-id> <task-id>
lab assistant task repeat <document-id> <task-id>
lab assistant subtab add "Notes" --parent <document-id> --parent-type note --top-level
lab assistant subtab add "More detail" --parent <tab-id> --parent-type note
```

Use the actual stored task/note type in tab parent references. Old `assistant
add` creates a document containing a task. Old `assistant set/done/repeat`
resolve a unique task ID into the new array; the document-scoped task commands
avoid ambiguity. `document set` edits document properties such as starred.
Direct Markdown edits remain supported; validate the full graph afterwards.
