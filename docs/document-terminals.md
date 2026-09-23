# Task and document terminal links

Opening Assistant, a task or a document never creates or wakes a terminal. Create the
terminals you want with **+ New** in the terminal bar, then link them:

- Drag an existing terminal tab onto a document row in Assistant.
- Inside a document, choose **Link terminal…**. Drag a terminal from the
  chooser onto an individual task, including a visible subtask, or select the
  task in **Terminal for task** and click an existing terminal.
- A linked task shows a **Terminal** button. Clicking it displays that exact
  session in the document modal. Reopening remembers the selected task terminal.
- **Unlink** removes only the association. It does not stop the process,
  delete its conversation, change its cwd, or alter its file/folder links.
  Terminal-tab secondary-click also offers **Unlink from task/document**.
- A task or document has one terminal owner; assigning another terminal
  transfers the link. Each terminal has one task/document association,
  independent of its file and folder/worktree associations.

Linked terminals show an accented task/document label in the terminal tab and
context header. Click the label to open the document modal over the current
workspace. Task links select the associated content tab, reveal and highlight
the exact task (including hidden or completed subtasks), and display its linked
terminal. Saved subtask and completed-task visibility preferences are preserved.
The underlying workspace and terminal selection stay in place.

The original process, conversation and unsent input stay in that session.
Linking does not send a prompt or replace the agent's startup instructions.
**Copy context** copies the document path and selected task identity for the
user to paste when needed. Task edits, priorities, status, content tabs and
nested subtabs retain their existing behavior.

The chooser lists existing running sessions across accessible workspaces and
vaults. A linked session that has stopped remains linked and shows its state;
click **Resume terminal** to deliberately restart that saved session. External
attached sessions use **Attach** in the terminal bar. Viewing, polling, hiding and
reopening documents never start replacement processes. The modal retains one
visible terminal renderer and WebSocket and releases them on close or hide.
Ordinary terminal lifecycle and close controls continue to own those processes.

## Storage and compatibility

The optional `linked_task` field belongs to durable workspace session metadata,
alongside `linked_file` and `linked_scope`. It contains the canonical
`assistant_root`, root `document_id`, optional JSON `task_id`, document `path`
and display `title`. A null task ID links the containing document. The server
resolves and validates the document and task in the client's configured
Assistant database; clients cannot select an arbitrary database root.

`PATCH /api/term/sessions/metadata` accepts
`linked_task: {document_id, task_id}` or `linked_task: null`, using the saved
session's logical `name`, `workspace_id` and `vault`. Link transfers are
serialized with file transfers, and every affected scope is authorized before
writes. `GET /api/term/task-terminals` lists running saved sessions; adding
`?document_id=<id>` lists that document's associations, including stopped ones.
Neither endpoint launches agents or sends terminal input.

No Assistant document migration is required. Existing JSON tasks, Markdown,
IDs, tab trees and saved provider conversations are unchanged. Update Lab and
reload each browser to use the manual linking UI.

## Previous managed document conversations

Previously created document conversations remain recoverable. When no manual
document link is selected, a saved sleeping conversation offers **Resume
previous conversation**. This is an explicit action; opening the document
does not resume it. Existing running managed conversations may be displayed.

Global → Documents settings apply only to these previous managed sessions:
`enabled` allows explicit resume, `sleepMinutes` controls the hidden idle
timeout, `maxRunning` is the idle cache budget, and `expireHours` expires only
unused bookmarks. Saved conversations, working agents, approval waits and
unsent drafts remain protected. These controls do not manage manually linked
ordinary terminals. The existing startup memory guard still applies to an
explicit legacy resume, and a waiting resume requires another deliberate retry.
