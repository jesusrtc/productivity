# Workspace objectives

An objective groups the work needed to solve one problem inside a workspace:
its outcome, worktrees, resources, task details and terminal associations.
The Home **Objectives demo** remains an independent browser sandbox. The
workspace feature stores real content and is enabled when its first objective
is created.

## Using the sidebar

Click **+ Objective** in a workspace. On the first creation, **Bring current
workspace worktrees, files and links** imports references to existing content.
The source files and links keep their ownership. Existing workspaces retain
their usual sidebar until they opt in.

The workspace tab bar starts with **All**, followed by **five objective slots**.
Filled slots show an objective's name and colored dot, using the vault-tab
style. Click one to open its tasks in the middle working area. Empty slots
remain available as drop targets and open the objective/slot chooser on click.
Objective selectors no longer occupy the left sidebar.

**All** lists every saved objective in the workspace. Search by name or outcome,
filter to focused/parked objectives, or filter by task status. **+ Objective**
creates an objective; when five are focused, choose the slot to replace. Drag a
row from All onto a tab to fill that exact slot. Dropping a parked objective on
an occupied slot replaces it; dragging between filled tabs swaps them. Parked
objectives retain their documents, tasks, worktrees and terminal associations.
**Focus…** provides the same assignment without dragging. The selected All or
objective view survives reload; startup reconciliation and file polls preserve
the newer working view.

Workspace Overview, Code Search, Jupyter, Logs and Cleanup tabs are removed.
Declared server tabs remain. Notebooks open from their resources or Files.
Global **Logs** and **Cleanup** sit together in the header.

The sidebar order is:

1. The Tasks item and its completion/status badge.
2. Shared documents, notebooks and links.
3. Fixed gray **Root** and **Objective** folders, then all associated worktrees.
4. Resources scoped to the selected folder or worktree.
5. The native recently updated files and Files tree for that selection.

**Root** always opens the workspace directory. **Objective** opens the selected
objective's own directory and changes when another objective is selected.
Both remain gray rather than taking a reserved worktree color. Creating an
objective creates its directory, including when it has no resources yet.

The **+** beside Worktrees uses the existing folder/worktree chooser, including
its create-worktree action. Association makes the worktree visible without
pinning it. A checkout can belong to one objective in this workspace. Each
objective has four reserved contrasting colors; assigned worktree colors are
unique across its workspace's objective registry.

Drag a resource onto a worktree to scope it to that checkout. It then appears
only while that checkout is selected. Drag it back into the shared resources
section to make it objective-wide again.

**Links** uses the same compact, one-line pills as workspace links. Each row
fits its label up to the sidebar width and shows the locally bundled service
icon inferred from its URL. Global **Links and icons** domain mappings also
apply here and update the rows immediately.

## Tasks and details

The Tasks item shows completed top-level tasks divided by total top-level
tasks. A parent with subtasks is complete when all its children are complete.
Checking a parent checks its children. The badge is green when everything is
complete, yellow when remaining work is on track, orange when an unfinished
deadline is within two calendar days, and red when unfinished work is overdue.
An undated child inherits its parent's deadline.

Tasks and subtasks occupy one line each in the working area, with a checkbox,
title, document button and due date. Every new task gets a mandatory details
subtab in an objective-owned `Tasks.md` document. Subtask details nest beneath
their parent's subtab. Clicking the document button opens those details as an
independent working view. Editing one subtab preserves its siblings.

## Documents, subtabs and notebooks

The Documents & notebooks **+** creates Markdown documents or `.ipynb` files,
or links an existing workspace file. Owned documents support Rename and new
subtabs. They open directly in the existing live Markdown editor:
click formatted text to edit it in place, type `/` for commands, or use the
editor's formatting shortcuts. **Save** and Cmd/Ctrl-S save immediately;
autosave runs after ten seconds without typing, and navigation saves the
outgoing draft. **Revert** loads the current saved version of that tab.
Unsaved drafts and editor undo remain available when switching between tabs.
Conflicts retain the draft and halt automatic retries until the user saves or
reverts; editing a subtab preserves its sibling content. Opening an owned
Markdown file from Files uses the same editor.

Notebook resources use the native cell editor, output
viewer, runtime controls and live execution path. Rename is available in the
notebook header. A running notebook must finish before it can be renamed; an
idle rename preserves the live kernel and its variables.

Click a document to reveal its nested subtab tree immediately. Hovering over
the document for 1.5 seconds also reveals it. Click a subtab to open it as its
own document view. Navigating to another sidebar item collapses the unpinned
subtabs; individually pinned subtabs remain visible and survive browser reloads.
Document subtabs live in the left menu, including for linked Assistant views;
there is no second tab rail inside the working area. Selected objectives,
worktrees and pins are browser-local preferences.

Assistant documents remain references to their original document IDs and
locations. Their original renderer, editing behavior, tasks and terminals
continue to belong to Assistant. Dragging an Assistant document to a workspace
tab keeps the workspace reference and also associates it with the selected
objective. A document can also be dropped directly into objective resources.

## Terminals

The native terminal selector groups sessions by the five focused objectives,
then by their fixed launch folders/worktrees. Sessions assigned to a parked
objective reappear when that objective is brought into focus. Existing native
terminal controls and sessions are reused. Rows stay flat, with a small objective
name and a thin objective-colored line down the left. Worktree groups use spacing
rather than extra boxes or headings. Shortcut and real checkout paths share the
same group.

Drop any sidebar object onto a **terminal name** to associate it with that
session: documents and subtabs, notebooks, links, Tasks, files, folders, Root,
the Objective directory, or a worktree. The reverse gesture works too: drag a
terminal onto a resource, Tasks, or a folder/worktree row. Clicking a linked
terminal reopens that object; Tasks opens the task list and folders use the
existing folder browser. Its corresponding sidebar scope is selected.
These mappings do not move the terminal's launch folder, transfer ownership,
change its Assistant document link, or replace its agent session.

Drop an object **inside the console** to paste its reference without submitting
input. Local objects use their captured absolute source path, external links
use their URL, and document subtabs retain `#tab=<id>`. Shell quoting preserves
spaces and special characters. Tasks uses its common details document when
there is one; empty lists or lists with multiple detail documents reference the
objective's entry in `.lab/objectives.json`. Console drops never create an
association. Ordinary workspace links and file/folder rows also support these
reference pastes.

## Storage and commands

The version-1 registry is `<workspace>/.lab/objectives.json`. Owned content
lives under `<workspace>/objectives/<objective-id>/` as ordinary Markdown and
notebook files. Markdown uses the existing embedded subtab format with stable
IDs. Assistant resources store references. Existing-file resources store their
folder and relative path. Terminal mappings use stable session UUIDs and one
target: a resource/subtab, file, folder, or `view: "tasks"`. Folder paths are
validated within the objective's workspace, own directory, or associated
checkout roots, including after resolving symlinks. The
existing `focused` array holds ordered objective IDs; empty slots can contain
`null`. Focus mutations accept a zero-based `slot` from 0 to 4. Older three-slot
registries remain readable without a migration.

Objective mutations use Lab's workspace lease and atomic writers. Browser
writes include the registry revision; document edits also include the content
revision. Stale writes are rejected and the current state is refreshed. A
resource unlink keeps its file, and a task's required details cannot be unlinked.

Use Lab rather than editing the registry by hand:

```bash
lab objective ls --workspace example
lab objective apply --workspace example --file /tmp/objective-action.json
```

An action file for first creation can contain:

```json
{
  "type": "create",
  "name": "Recover phone verification",
  "purpose": "Verify malformed input and record the fix",
  "import_existing": true
}
```

The authenticated UI reads and writes `/api/objectives`. Live notebook renames
should use that UI/API, which coordinates the rename with the kernel registry.
Notebook execution that should appear live in Lab continues to use
`lab notebook exec`.

## Performance and staging

Resources are available from the current objective payload, with a bounded
owned-content cache. Focused worktrees reuse the native bounded sidebar
projection cache. Task checks paint immediately and reconcile serially with
confirmed writes. Assistant navigation uses its existing inline renderer
without waiting for a terminal-selection lookup.

The `large-projects` workspace is the authorized staging target. Reproduction
scripts and the measured scope of the 200 ms target are recorded in
[the staging verification report](diagnostics/objectives-staging-2026-10-02.md).
