# Assistant: one documents folder and external documents

After unified storage, `lab migrations assistant-document-tasks` describes the
next migration to independent tasks inside each document. For a database marked
`task_format: "document-tasks-v1"`, use that guide for task lifecycle and commands.

This guide is read-only. It does not migrate data. Read the client's AGENTS.md
and README.md and obtain authorization for a migration before executing it.

## Current storage contract

Schema 2 uses `document_format: "embedded-subtabs-v1"` and, after this migration,
`storage_layout: "unified-documents-v1"` in `.assistant/manifest.json`.
Every independent task, note, meeting and series is `documents/<id>.md`.
Its subtabs remain embedded in that same file. Independent projects remain
`projects/<id>.md`; project/workspace relationships do not move documents.
Stored types `task` and `note` remain valid and immutable compatibility metadata.
Tracking, retention and labels determine the UI views independently of paths.
Read `lab migrations assistant-subtabs` for exact Markdown serialization.

The generated `.assistant/index.json` remains a disposable cache. The migration
maintains `path_aliases` (old physical root path → canonical document path) and
`document_origins` (canonical root path → previous root path) in the manifest.
These keep old Lab links, including `#tab=<id>`, and relative resource bases
working. Existing per-record aliases, legacy_path and unknown metadata survive.
Do not hand-edit the manifest or index, or rename the files with shell `mv`.
Old filesystem paths are logical aliases in Lab, not filesystem symlinks.
External tools that read a physical tasks/notes path must adopt documents/.

## Migrate each client

1. Update Lab to a version providing `lab assistant migrate --documents`.
   Read this guide with `lab migrations assistant-documents` on that client.
   Resolve the exact database with `lab assistant path`; use that client's
   `LAB_ASSISTANT_HOME` when necessary. Do not infer it from a workspace name.
2. Pause other editors and agent writes, stop the client's Lab backend, and
   keep it stopped until verification completes. Save any unsaved UI drafts.
   Make an additional whole-database backup if the client requires one.
3. Inspect the manifest. A workspace-folder database needs
   `lab assistant migrate --dry-run` then `lab assistant migrate --apply` first
   (read `lab migrations assistant-records-v2`). Schema 2 without embedded
   subtabs needs `lab assistant migrate --embedded --dry-run` then
   `lab assistant migrate --embedded --apply` (read `assistant-subtabs`).
   Skip these steps when already on that format.
4. For an embedded schema-2 database:

   ```bash
   lab assistant verify
   lab assistant migrate --documents --dry-run
   lab assistant migrate --documents --apply
   lab assistant verify
   lab assistant document ls
   ```

   Inspect the dry-run's move list before applying. Existing Markdown in
   documents/, destination symlinks, ambiguous references and colliding IDs
   fail before files move. Resolve such conflicts with the client; do not
   overwrite or delete the conflicting files to force the migration.
5. The command copies original Markdown, manifest and existing client guides to
   `.assistant/backups/documents-<id>/`, verifies SHA-256 hashes, records a journal
   in `.assistant/migrations/`, and enables maintenance state while moving data.
   Markdown moves byte-for-byte. It verifies metadata, bodies, subtab trees and
   old references after changing the layout. A normal failure rolls back.
   Repeating a completed migration is a no-op. Non-Markdown attachments stay at
   their original paths; only empty tasks/notes directories are removed.
6. Update only the client's obsolete *technical storage instructions* in
   AGENTS.md/README.md to use documents/ and this guide. Preserve every client
   content/writing rule. The migration deliberately does not overwrite them.
7. Restart that client's backend with the updated Lab code and reload the UI.
   Check a document, a nested tab, an old link, a relative asset if present,
   and the dashboard. New task/note creation should now write to documents/.

Backups and journals are retained. If the process is killed during migration,
keep editors and the backend stopped. Do not just flip `state` to active.
An agent should inspect the journal, verify each backup file against `sha256`,
restore the listed original files and manifest byte-for-byte, and remove only
new destinations listed in `moves` that still match those original bytes.
Preserve any changed destination separately. Rebuild the index with
`lab assistant verify` using the matching Lab version before restarting.
A rollback after subsequent user edits requires reconciling those edits first.

## Associated external document

A root document or subtab can own an optional `external_url` string. Use an
absolute HTTP(S) URL, without credentials or whitespace; `null` removes it.
The URL is a link, not imported content or an access grant. Sharing remains
controlled by the external provider. Subtabs do not inherit another tab's URL.

Set **External document URL** in the document header. **External doc ↗** appears
on its dashboard/list row, header, index and tab navigation; series history
has a link for each associated note. A collapsed series row links to the latest
note's external document; the series itself has a separate link in its header.

```bash
lab assistant document set <id> external_url 'https://docs.google.com/document/d/ID/edit'
lab assistant subtab set <id> external_url 'https://example.com/reference'
lab assistant document set <id> external_url null
```

These buttons open on the clicking client, including remote/SSH clients, and
never launch the Lab server's desktop browser. In a regular web browser they
open a new tab/window in that browser. A website cannot force a different OS
default browser on a remote machine; a PWA's handling follows the client/browser.
This optional metadata needs no data migration. It requires the updated Lab
code, and works with schema 2 both before and after the folder migration.
