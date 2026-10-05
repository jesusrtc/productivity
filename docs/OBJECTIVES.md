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

The workspace tab bar has **Objectives** and **the current objective**, using
the vault-tab style. Hover over the current objective to show the five focused
objectives in a dropdown. Choose one to open its full overview in the middle
working area, including every task, subtask and active asset. The arrow also opens the dropdown on click; Arrow Up/Down enters it from
the keyboard and Escape closes it. While working on a task, this same tab shows
the task's title and icon; its dropdown still switches objectives.

**Objectives** lists every saved objective in the workspace. Its top section
contains five numbered focus slots. Search the results by name or outcome,
filter to focused/parked objectives, or filter by task status. **+ Objective**
creates an objective; when five are focused, choose where to insert it. Drag a
result onto a slot to insert it at that position. Following objectives move
down and the previous fifth objective is parked. Moving an already focused
objective removes its former position and reorders the list without a duplicate.
Placement keeps the library open for further arranging. Empty slots can also
be clicked to choose an objective. Parked
objectives retain their documents, tasks, worktrees and terminal associations.
**Focus…** provides the same assignment without dragging. The selected library or
objective view survives reload; startup reconciliation and file polls preserve
the newer working view.

Workspace Overview, Code Search, Jupyter, Logs and Cleanup tabs are removed.
Notebooks open from their resources or Files. Global **Servers**, **Logs** and
**Resources** remain in the header; cleanup is reviewed inside Resources.

The sidebar order is:

1. The **Objective name**, followed by **Objective · pinned** assets when any
   are starred. Pinned assets stay above Tasks in every working view.
2. **Tasks**, completion/status badge, task links and status context menu.
3. **Task assets**, including the selected task's mandatory details and attachments.
4. **Unassigned** assets with neither a shared star nor a task association,
   shown only while the Objective overview is open.
5. Collapsed **Archive** in the Objective overview, then fixed gray **Root** and
   **Objective** folders in every view.
6. The native recently updated files and Files tree for that selection.

Click the **Objective name** to leave task mode and open its overview. The
middle column puts **Unassigned assets** first, with suggestion status and
assignment controls. Tasks without optional attachments precede tasks with
assets; required task specifications are always retained. The toolbar offers
**Tasks with assets**, **Tasks only**, **Unassigned assets**, and **Archive**.
Search filters as you type by task title, asset name or reference/path. A task
match includes all its assets; an attached asset match includes its owning task
and attachments. Global/shared assets and a collapsed complete catalog follow.
Assets in other worktree scopes remain visible in this overview. Archive stays
excluded until its view is selected. Search and view choices are remembered per
Objective. The Objective name is also a full-context drag source.

Click **Unassigned** to open its review view. Choose **Tasks with assets** to
drag assets onto task rows. Each asset, document subtab, link child and associated worktree
has a **☆/★** control. Starring adds shared Objective context without removing
any task associations; unstarring keeps task associations. The **⋯** menu
classifies an asset as Unassigned, Objective, a particular task, Archive or Trash.
Secondary-click an asset for **Move to task**, **Move to Objective**, **Unassigned**,
**Archive** and **Trash**. Task/Objective pickers can select another Objective in
the same workspace. Manual moves replace optional task membership; stars remain
additive. While a task, document or folder is open, unassigned assets and Archive
are hidden; pinned assets and the selected task's own assets remain available.
Bucket drops provide the same classification. Moving to Unassigned removes
optional task associations and shared pins. Archive removes those associations
but retains the source for recovery; expand it to move references back. A task's
mandatory details cannot be detached or archived. Only registered references
appear in Unassigned; the native Files tree supplies additional sources.

**Trash** requires confirmation and removes the asset registration and its
optional task attachments. It preserves source files, original Assistant
documents and running terminals. Trashing an individual document subtab or link
child hides that asset reference while retaining the containing document/link.
Required task details and fixed Root/Objective folders cannot be trashed.

## Suggested assignments

Agents infer asset organization by creating `suggest-assignment` records, using
`lab objective apply --workspace <id> --expected <revision> --file <action.json>`.
See `lab context objectives` for exact action examples and target rules. A
proposal records an existing asset, destination task/subtask or Objective, and a
reason. It changes no real assignment, star, worktree membership or terminal.

The Objective review shows **Suggestion available**, **No suggestion** or
**Suggestion rejected** beside each unassigned/global asset. **Accept** applies
the proposed relationship atomically; **Reject** keeps the asset in place.
**Choose another** opens the manual picker. Identical rejected proposals stay
rejected across subsequent agent runs. Changed or missing destinations and stale
revisions cannot silently commit a proposal. Cross-Objective moves retain the
original file ownership: owned files become references from the destination.

Associated worktrees are assets too: an unclassified worktree appears in
Unassigned; dropping it on a task puts it in that task's context. Every associated
worktree also stays in the **Worktrees** section, regardless of the selected
task or working view. Root and Objective folders come first, followed by
Unassigned, Objective-pinned and task groups. A worktree attached to multiple
tasks appears once in this navigation section under a combined task label.
Task/subtask labels preserve their parent context. Shared pins and task asset
lists continue to show their contextual references. Archived worktrees remain
recoverable in a collapsed Archive group in the Worktrees section. Worktree
rows retain their folder navigation, drag targets, stars and classification
menus. Root and Objective remain gray draggable terminal references.
Files and folders inside the native explorer have no stars or classification
controls; the worktree is the asset. A file dragged onto a task or explicitly
linked as an asset still gets its own asset controls in the buckets.

**Root** always opens the workspace directory. **Objective** opens the selected
objective's own directory and changes when another objective is selected.
Both remain gray rather than taking a reserved worktree color. Creating an
objective creates its directory, including when it has no resources yet.
Clicking Root, Objective or a worktree exits task focus, selects that exact file
scope and shows the native Files tree, including when it was already the selected
scope. Recently updated, vs main and Uncommitted retain their current settings.
Plain scope clicks do not open a folder modal. GitHub history and terminal
actions remain explicit buttons on the selected scope row.

The **+** beside Worktrees uses the existing folder/worktree chooser, including
its create-worktree action. Association immediately shows the checkout in the
Worktrees section's Unassigned group, ready to attach to a task or star as shared context. A checkout can
belong to one objective in this workspace. Each
focus slot has a fixed objective color and four reserved contrasting worktree
colors. An objective and its worktrees adopt the destination slot's palette
when inserted or moved; shifted objectives also adopt their new slot colors.
Parked objectives are gray. Extra worktrees receive distinct colors outside the
reserved palettes. Older registries adopt slot colors on read without rewriting
their content or order.

Drag a resource onto a worktree to scope it to that checkout. It then appears
only while that checkout is selected. Star it to include it in shared Objective
context across tasks, including when its checkout is not selected. This preserves its original checkout association.

Links in each asset bucket use the same compact, one-line pills as workspace
links. Each row fits its label up to the sidebar width and shows the locally bundled service
icon inferred from its URL. Global **Links and icons** domain mappings also
apply here and update the rows immediately.

Click a link to visit its URL directly in the clicking browser, leaving the
working area in place. Cmd/Ctrl-click opens its details in the middle working
area. Edit its title,
URL, TL;DR and named metadata properties, then use **Save** or Cmd/Ctrl-S.
**Revert** reloads the saved details. Drafts remain available when navigating
away; a conflicting edit retains your draft. **Open** visits the URL in the
clicking browser. These controls apply to shared and scoped links, as well as
links attached to tasks.

Use **+ Sublink** in a link's details to add destinations beneath it, such as
Google Docs tab URLs. Each sublink has its own title, URL, TL;DR and properties,
and can contain further sublinks. Hover over the parent sidebar link for one
second to reveal the indented hierarchy. Clicking a child opens its destination;
Cmd/Ctrl-click opens its own details. Child references can be pasted
or associated with terminals just like their parent link.

## Tasks and details

The Tasks section shows completed top-level tasks divided by total top-level
tasks. A parent with subtasks is complete when all its children are complete.
Checking a parent checks its children. The badge is green when everything is
complete, yellow when remaining work is on track, orange when an unfinished
deadline is within two calendar days, and red when unfinished work is overdue.
An undated child inherits its parent's deadline.

Tasks and subtasks occupy one line each in the working area, with a checkbox,
title, document button and due date. Every new task gets a mandatory details
subtab in an objective-owned `Tasks.md` document. Subtask details nest beneath
their parent's subtab. Clicking the task title opens those details as an
independent working view. Editing one subtab preserves its siblings.

The left task list opens task details on a normal click. Selecting a task expands just that
parent's subtasks and displays its own assets beneath the list. Selecting
another parent collapses the previous group. Task details are not duplicated
as a separate `Tasks.md` tree in Unassigned.

Clicking a task or subtask also opens its linked terminal and reveals the
terminal panel. Its details stay open. If several terminals belong to that
task, keep the current one when it is linked; otherwise select the first
available terminal. A terminal has one task/subtask assignment at a time:
linking it to another task replaces the previous assignment, including across
Objectives. Tasks without a linked terminal leave the current terminal alone.

Task titles are hyperlinks to their required details document/subtab. Clicking
a title opens those details and enters task mode. Its working-area header keeps
the task's name, completion checkbox, **Edit task** and **Off · Semi · Focus**
visible while browsing assets. Click the header's task name to return to details.
Focus hides the native Files tree; the four asset/task buckets remain available.
Semi keeps the full sidebar and highlights shared, parent and task context in
its existing order. Off shows the full sidebar without highlights. Returning
to Tasks or switching objectives exits task mode. The red **×** in the working
area's upper-right corner closes task mode and returns to the task list. It
remains available while browsing native assets, follows the working viewport,
and stays above the native notebook toolbar. Navigation saves outgoing document
drafts. The selected mode is browser-local.

Drag documents, document subtabs, notebooks, links, sublinks, files, folders or
worktrees onto a task row to attach references. Assets can also be dropped onto
the selected Task assets bucket or the task's asset-list dialog. Existing files
and Assistant documents are linked without copying content. Shared/worktree
scopes and original ownership remain unchanged. Duplicate drops keep one
association. The middle task-list asset button opens its attachments and can
detach optional assets; its mandatory details remain associated.

The left edge of each task row shows **⬜** for Undo with a red frame, **🟡** for
In progress and **✅** for Completed. Secondary-click anywhere on the row to
choose **Set to completed**, **Set to undo** or **Set to in progress**. The menu
also opens with Shift+F10 and closes with Escape. Completed and Undo update
the task's subtasks too; In progress preserves their completion. Changing a
subtask updates its parent's aggregate status. Status is saved in the Objective
manifest and reflected in the task header, active tab and default terminal icon.
The right edge holds the icon used by its active tab and linked terminals.
Without a chosen asset, the right edge shows no icon. Its empty drop area
appears on hover or keyboard focus so an asset can still be dragged there.
The active tab and linked terminals use the task's current status by default.
Attaching assets and editing task details keep the chosen icon. Only dropping
an asset onto the task's icon area chooses that asset's icon, attaching it if necessary. The current tab and a terminal
linked to the task inherit the icon. Existing saved icon choices remain valid;
removing the chosen asset restores the status icon.

## Documents, subtabs and notebooks

The Unassigned **+** creates Markdown documents or `.ipynb` files,
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

Resource icons use the shared Files extension mapping, including Jupyter for
`.ipynb` and database icons for `.sql`, even when imported as generic file
references. Assistant references keep their internal document icon.

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

**+ New** asks whether to open for the current workflow (workspace root), the
current Objective (its own directory), or a specific worktree in that Objective.
The worktree option opens a list restricted to that Objective's associated
checkouts. Objective choices save a whole-Objective terminal association;
worktree choices save a folder association. The Home demo offers the same
choices with simulated terminals. See [TERMINALS.md](TERMINALS.md#new-terminal-location).

The native terminal selector groups sessions by the five focused objectives.
Within each Objective, terminals assigned to the whole Objective come first,
then terminals follow the sidebar task order: each parent task followed by its
subtasks, then the next parent. Multiple terminals for one task keep their
relative order. Terminals without a task assignment, including those linked
only to an asset or folder, come last. Task order takes priority over launch
folder grouping and updates after task creation, reassignment or reload.
Sessions assigned to a parked
objective reappear when that objective is brought into focus. Existing native
terminal controls and sessions are reused. Rows stay flat, with a small objective
name and a thin line down the left. Only the current objective uses its colored
line and worktree labels/dots; other groups keep a colored header and neutral
lines and associations. Working/completion indicators retain their status
colors. Worktree groups use spacing
rather than extra boxes or headings. Shortcut and real checkout paths share the
same folder identity; spacing marks consecutive sessions from that folder.

Drop the Objective name onto a terminal name, or a terminal onto the sidebar's
Objective name, to assign it to the whole Objective. Clicking that terminal
opens the Objective overview. This keeps its launch folder, process, display
label and original owner. Dropping the Objective inside the console still
pastes its full unsent context instead of creating an assignment.

Drop any sidebar object onto a **terminal name** to associate it with that
session: documents and subtabs, notebooks, links, Tasks, files, folders, Root,
the Objective directory, or a worktree. The reverse gesture works too: drag a
terminal onto a left-column task, resource, Tasks, or folder/worktree row.
Middle-column elements reject terminal association drops. Clicking a linked
terminal reopens that object; Tasks opens the task list and folders use the
existing folder browser. Root, Objective and whole-worktree links instead
select the native Files tree. Its corresponding sidebar scope is selected.
These mappings do not move the terminal's launch folder, transfer ownership,
change its Assistant document link, or replace its agent session.

Drop an object **inside the console** to paste its reference without submitting
input. Local objects use their captured absolute source path, external links
use their URL, and document subtabs retain `#tab=<id>`. Shell quoting preserves
spaces and special characters. Tasks uses its common details document when
there is one; empty lists or lists with multiple detail documents reference the
Objective's `.objective.json#view=tasks`. Legacy workspaces still reference
their original registry until converted. Console drops never create an
association. Ordinary workspace links and file/folder rows also support these
reference pastes.

Drag a task title or the focused task control onto a terminal name to link that
terminal to the task. The reverse terminal-to-task-row drop also works in the left column. Clicking
the terminal opens the task's details in Focus mode. Its launch folder, process
and original Assistant ownership remain intact.
Dropping a terminal onto a task or subtask also renames its display label to
that task's current name. The label is saved on the terminal's original owner
and remains after reload; later manual terminal renames are still available.

Dropping a task **inside the console** pastes an unsent prompt. **Context:**
identifies the Objective and its shared assets, then each parent task's details
and assets. **This task:** identifies the selected task and its exact details
subtab and assets. Every reference has a title and type, such as task
specification, notebook, SQL file, link, document tab or worktree. Exact paths,
tabs and sublinks are preserved; repeated references use the same `[R#]` label
and Archive is excluded.

The prompt directs the agent to work only on the selected task. Objective and
parent references are background context, read-only unless also attached to
the selected task. Changes stay within its references and explicitly linked
worktrees/folders, preserving parent and sibling specifications. Agent editors
receive the readable multiline prompt through bracketed paste; consoles that
do not support it receive one line to avoid accidental submission. No Enter
is sent. Ordinary asset drops keep their existing shell-quoted reference paste.

Drag the current Objective tab, its focus-menu entry, the left **Objective**
heading or its library row into a console to pass the whole Objective. The
unsent **This objective:** prompt includes its outcome, manifest and folder,
every task/subtask's details and attachments, all active registered resources,
document tabs, sublinks and linked worktrees. This includes Unassigned and
worktree-scoped resources. Archive and unregistered explorer files are excluded.
Each source is defined once, with its roles retained across tasks. Focus-slot
drops still move the Objective; a console drop preserves all associations.
The prompt separates the Objective index, global assets shared across tasks,
each task/subtask's specification and assets, Unassigned assets, and a complete
asset index grouped by type. Repeated sources retain the same reference label
so an asset's global and task roles remain clear.

## Storage and commands

Each Objective's source of truth is
`<workspace>/objectives/<folder>/.objective.json`. Lab discovers these files
directly, including files created or edited outside Lab. The folder name may
differ from its stable Objective ID. New UI-created Objectives currently use
their ID as the folder name. The version-1 manifest owns its name, purpose,
resources, worktrees, tasks and shared/task/archive associations.

Owned Markdown and notebooks live beside the manifest; their stored `path`
is relative to that Objective folder. Markdown uses the existing embedded
subtab format with stable IDs. Assistant resources retain their original
location and ID references. Existing-file resources retain their source folder
and relative path. Links are `kind: "link"` manifest entries; they do not need
individual files. Unregistered explorer files are not automatically assets.
All asset definitions and their global/task indexes belong to this Objective's
manifest in its directory. Linked remote documents, Assistant content, source
files and worktrees are represented there by their exact source references.

Only UI/runtime preferences live in `.lab/objectives-state.json`: enabled state,
ordered Objective IDs, the five focused IDs and terminal mappings. This file
contains no Objective resources, tasks or content. Slot colors are computed.
Terminal mappings use stable session UUIDs and one
target: a resource/subtab/sublink, file, folder, or `view: "tasks"`. External link
details use optional `tldr`, `metadata` and nested `sublinks` fields. Sublinks
have stable IDs; terminal mappings use `sub_link_id` to retain the exact target.
Removing a sublink falls back to its parent resource for associated terminals.
Existing link fields remain readable. Folder paths are
validated within the objective's workspace, own directory, or associated
checkout roots, including after resolving symlinks. The
state file's `focused` array holds ordered Objective IDs; empty slots can contain
`null`. Focus mutations accept a zero-based `slot` from 0 to 4. Older three-slot
legacy registries remain readable without modification.

Objectives can have optional `shared_assets`, `archived_assets` and `asset_shelf`
reference lists. These are read as empty when absent, without rewriting the
manifest or changing its version.

Tasks can have optional `assets` entries with stable IDs targeting resources,
document subtabs, link children or folders. `icon_asset_id` selects an asset's
display icon; `details` selects the mandatory task details. Terminal mappings
can use `task_id` instead of another target. Legacy tasks need no migration.

Objective mutations use Lab's workspace lease, a workspace-specific metadata
writer lock and atomic writers. Unchanged sibling manifests are not rewritten.
Browser writes include the combined file/state revision; document edits also include the content
revision. Stale writes are rejected and the current state is refreshed. A
resource unlink keeps its file, and a task's required details cannot be unlinked.

Manifests may be edited directly. Use Lab for validated mutations, live notebook
renames and converting the previous `.lab/objectives.json` format:

```bash
lab objective ls --workspace example
lab objective apply --workspace example --file /tmp/objective-action.json
lab objective migrate --workspace example
lab objective migrate --workspace example --apply
```

Migration previews make no changes. Applying preflights all files, retains a
byte-identical `.lab/objectives.legacy.json` backup, writes per-folder manifests,
then removes the old registry. IDs, unknown fields, document bytes, subtabs,
task associations and Assistant ownership are preserved. Interrupted migrations
can be retried. Ordinary reads do not convert old data; the first successful
Objective mutation does. Invalid actions do not migrate it.
See `lab migrations workspace-objectives` for the format and migration guide.

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
The additional resource/task cases and live notebook checks are recorded in
[the asset-case report](diagnostics/objectives-asset-cases-2026-10-02.md).
The live task/asset sidebar and final icon behavior are verified in
[the live-sidebar report](diagnostics/objectives-live-sidebar-2026-10-03.md).
Run `scripts/perf/seed_objective_asset_cases.py` with an explicit staging
`LAB_VAULT`; `--execute-notebooks` streams the synthetic evidence through Lab.

## Asset buckets in the Home demo

**Home → Objectives demo** now follows the production shell: Objectives and
one current objective/task tab, a five-choice hover menu, five ordered library
slots, flat terminal groups and the native inline Markdown editor. Its data
and terminals remain simulated; only browser-local demo state is saved.
Normal reloads version both the shell assets and the sandbox's scripts/styles,
including its native Markdown editor.

Like the live sidebar, the demo order is **Unassigned**, **Objective · pinned**,
**Tasks**, then **Task assets**. Unassigned contains registered assets that
have neither a shared pin nor a task association. Shared Objective pins apply
to every task. Clicking a task opens its details and lists its own assets below
the task list. Documents, subtabs, notebooks, external links, files, folders
and worktrees all use this reference-based classification.

The left task list opens details and has the same secondary-click status menu
as the live workspace. Completion and editing also remain available in the
middle task view. Selecting a task expands only that task's subtasks; selecting
another collapses the previous group. The live and demo lists reserve space
for the largest subtask group in the Objective, so **Task assets** stays at the
same position while navigating tasks, subtasks or closing task mode. Task mode keeps the task's name, icon,
completion control and red corner close visible while browsing its assets.
Click the task name in that header to return to its details.

Drag an asset onto any task row to attach it. Drop it into Objective to pin it
as shared context. The **⋯** on an asset also chooses its bucket and task.
Every asset and individual document subtab has a **☆/★** control that toggles
shared Objective context without removing its task associations. Drop an
asset onto a task's icon area to select that icon and attach the asset if
needed. Tasks default to ⬜ / 🟡 / ✅, and the current tab and linked terminal inherit the
right-side asset icon when chosen. Clicking
**Unassigned** opens the middle task list, where asset drops attach to tasks.
Dropping into Unassigned removes optional task associations and shared pins.
**Archive** keeps sources available for recovery while removing them from
shared/task context; expand it and move an asset back to recover it. Mandatory
task details cannot be detached or archived. Worktrees follow the same asset
buckets as documents and links; the demo includes an Unassigned triage
worktree to try attaching it. The gray Root and Objective rows remain visible
outside the collapsible **Files** explorer. Its file/folder rows have no stars
or classification controls and supply additional sources without listing every
checkout file as unassigned.

Drop a task onto a simulated terminal name to associate it. Drop it inside the
console to paste the same scoped **Context:** / **This task:** prompt as the
live console, with shared Objective references, parent details/assets and the
selected task's specification and assets. Reference types and exact sources
remain explicit, with repeated sources linked by `[R#]` labels
and Archive excluded. Drag an Objective title or its left heading into the
console for the same whole-Objective prompt. Drag a simulated terminal onto a left-column task,
document/subtab, file, folder or worktree to associate it; middle-column
elements reject terminal association drops. No input
is submitted until **Run simulation**. External-link clicks are simulated;
Cmd/Ctrl-click shows their editable metadata. **Reset demo** restores the
sample data. The demo uses the same workflow as the live sidebar but keeps its
state and simulated terminals separate from workspace data.
