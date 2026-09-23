# Tasks inside documents

Documents is the production library. Single-click a document to open it inline
in the main workspace area; double-click to open its modal. **Expand** moves an
inline document into the modal while preserving its editor and draft. Closing
returns to the document list. The existing saved dashboard
sections, filter JSON, independent document/series/note stars, series history,
external links, content editor, heading copy, tab creation and nested subtabs
remain in place. There is no separate prototype view.

Drag the divider beside the document tabs to resize their column. The browser
remembers the width across documents and inline/modal views. The range is
160–600 pixels, limited by the space available for the document. Double-click
the divider to reset, or focus it and use the arrow keys to resize.

The header groups actions separately from key task and meeting properties.
**Copy** offers Google Docs and plain-text formats. **Properties** contains
document details, organization, tracking, external URL and custom attributes.
Recent content-tab changes use small blue dots for updates and green dots for
new tabs. Hover reveals the change time; dismissal and three-day expiry remain
available without opening a tab clearing its marker.

A document owns a single JSON `tasks` array in its Markdown frontmatter and
`task_format: "document-tasks-v1"`. Content tabs are always untracked. A task
has a stable `id`, `title`, `priority`, `status`, optional `parent_id`, and an
optional `tab_id` pointing to the root content tab or an embedded tab. A null
link is a quick action without a content tab. A child without an explicit link
inherits its parent task's link. Task parentage and tab parentage are separate.

Statuses are `not_started`, `in_progress`, `blocked`, `done`, `skipped`, and
`cancelled`. Parent completion derives from task children. Explicit WIP/blocked
on an incomplete parent does not start its children; completing every child
clears that override. Completion checkboxes complete/reopen a branch. Completed
titles are readable without strikethrough or dimming.

The document's Dashboard displays all task-bearing tabs as sibling task groups
and links to every content tab. Opening a content tab shows its own direct
tasks above its notes. **Mostrar todo** adds task subtasks and task-bearing
content descendants; **Mostrar menos** restores the default. **Solo WIP** filters
the selected scope. Each new opening starts with only direct tasks. Clicking a
linked task title opens its content tab. There is no redundant tab-link button.
The last selected content tab or Dashboard is remembered per browser/database.

The document list retains compact 40px desktop rows and stars, and shows
pending/WIP/blocked counts. Pending totals count unfinished leaf tasks once.
A WIP/blocked parent counts only if no descendant already has that status.
The existing home dashboard evaluates its unchanged filters against the new
work records; it does not store another copy of task state.

The task menu edits title, tab link, due date, owner, recurrence, planning and
follow-up properties, and custom attributes. It can add ordinary subtasks or
delete a task branch. Task controls add work without creating content tabs.
The rail's + still adds a content tab; **Add subtab** nests a content tab.
**Add task** in a tab's menu creates a task linked to that existing tab.

Recurring tasks explicitly create their next occurrence in the same document,
retaining the old occurrence and resetting a copied task/subtask branch. The
operation is idempotent for the same prior occurrence and next date. A valid due
date is required; no deadline is inferred.

`POST /api/assistant/document-task` and `/document-task/repeat` require an admin
session and the document's expected SHA-256 revision. Writes share the database
file lock used by content and metadata edits, validate hierarchy/links/fields,
and atomically replace only the owning document. A stale revision returns 409;
no other edits are overwritten. Note drafts and custom document/tab metadata
remain independent of task edits. Legacy storage clients remain readable until
explicit migration.

Read `lab migrations assistant-document-tasks` for the migration, backup, and
recovery contract. Task content is client-owned; the framework never seeds demo
content or changes a client's writing conventions.

## Adopting this change on another client

Update that client's Lab installation from `origin/main`, then run
`lab migrations assistant-document-tasks` there. The packaged Lab agent context
and `lab context tasks` point agents to this guide; `lab migrations` lists it.
A code update does not automatically migrate another client's database.

Resolve its database with `lab assistant path`, read its own instructions, save
drafts and stop its backend. Inspect `lab assistant migrate --document-tasks
--dry-run`, apply with `--apply`, and run `lab assistant verify`. The guide covers
older storage prerequisites, verified backups, recovery, and the restart checks.
A second dry run should report no changes. Update only obsolete technical
instructions in the client's guides and restart the updated backend.

Agents and integrations can inspect the manifest's `task_format` marker. For
`document-tasks-v1`, use each document's task array and the document-scoped task
commands/API; keep tab creation, note bodies, stars and dashboard settings on
their existing interfaces. Legacy tracked-tab commands remain compatibility
paths where a task ID resolves unambiguously.
