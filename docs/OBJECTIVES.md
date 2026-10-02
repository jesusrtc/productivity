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

Up to three objectives appear at the top of the left column. Click one to open
its tasks in the middle working area. The **+** beside Objectives creates or
brings back an objective; when three are focused, choose which slot to replace.
The parked objective retains its documents, tasks, worktrees and terminals.

The sidebar order is:

1. Focused objective selectors.
2. Shared documents, notebooks and links, then one Tasks item.
3. All worktrees associated with the selected objective.
4. Resources scoped to the selected worktree.
5. The native recently updated files and Files tree for that worktree.

The **+** beside Worktrees uses the existing folder/worktree chooser, including
its create-worktree action. Association makes the worktree visible without
pinning it. A checkout can belong to one objective in this workspace. Each
objective has four reserved contrasting colors; assigned worktree colors are
unique across its workspace's objective registry.

Drag a resource onto a worktree to scope it to that checkout. It then appears
only while that checkout is selected. Drag it back into the shared resources
section to make it objective-wide again.

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
or links an existing workspace file. Owned documents support Edit, Save,
Rename and new subtabs. Notebook resources use the native cell editor, output
viewer, runtime controls and live execution path. Rename is available in the
notebook header. A running notebook must finish before it can be renamed; an
idle rename preserves the live kernel and its variables.

Click a document to reveal its nested subtab tree immediately. Hovering over
the document for 1.5 seconds also reveals it. Click a subtab to open it as its
own document view. Navigating to another sidebar item collapses the unpinned
subtabs; individually pinned subtabs remain visible and survive browser reloads.
Selected objectives, worktrees and pins are browser-local preferences.

Assistant documents remain references to their original document IDs and
locations. Their original renderer, editing behavior, tasks and terminals
continue to belong to Assistant. Dragging an Assistant document to a workspace
tab keeps the workspace reference and also associates it with the selected
objective. A document can also be dropped directly into objective resources.

## Terminals

The native terminal selector groups sessions by the three focused objectives,
then by their fixed launch folders/worktrees. Sessions assigned to a parked
objective reappear when that objective is brought into focus. Existing native
terminal controls and sessions are reused.

Drag a resource, subtab or file onto a terminal to associate that working view
with the session. A terminal can also be dropped onto an objective resource.
Clicking an associated terminal opens its resource and selects the relevant
worktree. These mappings do not move the terminal's launch folder, transfer
ownership, change its Assistant document link, or replace its agent session.

## Storage and commands

The version-1 registry is `<workspace>/.lab/objectives.json`. Owned content
lives under `<workspace>/objectives/<objective-id>/` as ordinary Markdown and
notebook files. Markdown uses the existing embedded subtab format with stable
IDs. Assistant resources store references. Existing-file resources store their
folder and relative path. Terminal mappings use stable session UUIDs.

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
