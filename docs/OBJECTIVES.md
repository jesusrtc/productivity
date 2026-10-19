# Workspace objectives

An objective groups the work needed to solve one problem inside a workspace:
its outcome, worktrees, resources, task details and terminal associations.
The Home **Objectives demo** remains an independent browser sandbox. The
workspace feature stores real content and is enabled when its first objective
is created.

## Pending tasks and action deadlines

The task sidebar shows unfinished task and subtask navigation. Unchecked action
items from each task's own Markdown tab appear in the main Tasks dashboard and
the source document; they do not add rows or reserved space to the left sidebar.
Completed and **Won’t do** tasks are excluded by default. **Show completed / discarded**
reveals task history. Repeating tasks waiting for reactivation remain hidden,
including their descendants; then the same branch returns unchecked.

An action item can carry an optional deadline immediately after its checkbox:

```markdown
- [ ] [2026-10-15 09:30] Review the proposal
- [ ] [2026-10-16] Send the approved summary
- [ ] An action without a deadline
```

Dates and times use the viewing browser's local time; date-only deadlines end
at the end of that day. Invalid date prefixes remain ordinary action text.
Actions without their own date inherit the task's deadline when available.
The dashboard lists overdue work and deadlines within two days, earliest first.
Click an action to open its containing document and tab, reveal folded content,
scroll to the item and highlight it. In Edit mode, its source line is selected.
Navigation and highlighting leave the Markdown unchanged.

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

1. The **Objective name**.
2. **Worktrees**, folded by default and opened only by clicking its header.
   Hover and keyboard focus leave it folded. Clicking elsewhere folds the list
   while preserving the selected checkout and its Files/assignment view.
   Each worktree has a down-arrow beside Terminal. Select its row, then click
   the arrow to fetch `origin/master` and rebase the current worktree branch onto
   that fetched commit. The result window shows Git output. Local tracked edits
   use Git's autostash; conflicts remain available to resolve, continue or abort.
   This does not switch branches, update sibling branches or push. A repository
   without remote `master` reports an error rather than substituting a branch.
   **Objective · pinned** assets follow Worktrees when any are starred and stay
   above Tasks in every working view.
3. **Tasks**, completion/status badge, task links and status context menu.
4. **Task assets**, including the selected task's mandatory details and attachments.
5. **Worktrees** for the selected task, directly below Task assets. Whole checkout
   references appear here with their existing actions; Root/Objective folders
   and checkout subfolders remain in Task assets.
6. **Unassigned** assets with neither a shared star nor a task association,
   shown only while the Objective overview is open.
7. Collapsed **Archive** in the Objective overview.
8. Native recently updated files and the Files tree for the selected worktree.
   Task mode shows recent files across only the worktrees assigned to that task.

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

Choose **Group asset…** in an asset's **⋯** menu to create a named group or add
it to an existing group. Groups have one level of children, revealed after a
one-second hover; clicking the group also opens it. Moving away cancels a pending
reveal. Drag an existing Objective asset onto a group header to add it. Asset
menus offer **Remove from group** and **Move up / Move down**; group menus offer
**Rename group…**, ordering and **Ungroup assets**. Ordering survives reload.
Groups apply within the Objective and show the members belonging to each
current task or bucket. They retain the original references, URLs (including
Google Doc section fragments), task assignments, stars and terminal links.
Grouping is always the client's choice; matching URLs do not create groups.

Every group and ordering operation is also available through the CLI:
`lab objective ls --workspace <id>` returns group IDs, membership, order and the
current revision. Write a JSON action and run
`lab objective apply --workspace <id> --expected <revision> --file <action.json>`.
The actions are `asset-group-create`, `asset-group-member` (including removal
with `group_id: null`), `asset-group-rename`, `asset-group-ungroup` and
`asset-order`. Read `lab context objectives` for their fields.

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
the associated checkout buttons. The list has no task or assignment-group
headings. A worktree attached to multiple tasks appears once. Shared pins retain
their contextual references; each task's checkout references appear in its own
Worktrees section below Task assets. Archived worktrees remain
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
scope. Recently updated appears on the left and all tasks/subtasks unfold in
the middle so a worktree can be dragged onto multiple tasks. Explicitly folding
the open Worktrees header restores the previous task and its assets. Opening a
checkout from the task Worktrees section keeps the top navigation folded.
Exactly one assigned worktree replaces
a task's displayed name with its name and color. With zero or multiple assigned
worktrees, the task keeps its own name, including in task headers and terminal
tabs. Its own Markdown, icon, context and assets remain.
Recently updated, vs main and Uncommitted retain their current settings.
**vs main** combines committed differences from local `main` with all staged
and unstaged files from **Uncommitted**, deduplicated within each checkout.
A local reversion to main still appears; changes in the index and working tree
cannot cancel a file out of the list. Tracked-file, hidden-file and extension
filters continue to apply.
Unavailable comparisons share one compact notice instead of repeating a message
under every worktree. Available checkout file results remain visible; empty
scopes are omitted, and an entirely empty list shows one quiet message. Local
main still compares with the exact local `main` ref. Choose Uncommitted or a time
filter when that comparison is unavailable; there is no remote-branch fallback.
Plain scope clicks do not open a folder modal. GitHub history and terminal
actions remain explicit buttons on the selected scope row.

The **+** beside Worktrees uses the existing folder/worktree chooser, including
its create-worktree action. Association immediately shows the checkout in the
Worktrees section, ready to attach to a task or star as shared context. A checkout can
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

Click a link to visit its URL in a separate pop-out positioned over Lab, leaving the
working area in place. Cmd/Ctrl-click opens a browser tab. Secondary-click the
asset and choose **Edit** to open a modal over the current view, including from
the task Assets dialog. Edit its title, URL, TL;DR and named metadata properties,
then use **Save** or Cmd/Ctrl-S. Close or Escape returns to the underlying view.
**Revert** reloads the saved details. Drafts remain available when navigating
away; a conflicting edit retains your draft. **Open** visits the URL in the
same kind of pop-out. These controls apply to shared and scoped links, as well as
links attached to tasks.

The same context menu offers **Copy URL** and **Open in Chrome** for URL
assets and their individual sublinks, including the Task assets dialog.
Copy puts the selected item's full saved URL on the clipboard and confirms
the result. Open in Chrome launches Google Chrome explicitly from a local
owner session. Remote sessions open their own Chrome tab; another remote
browser shows instructions and a manual browser link. Query parameters and
fragments are preserved, and neither action edits the asset or its assignments.
Agents can select both actions with `lab ui contextmenu`, `inspect` and `click`.

Every click opens a new pop-out immediately, including repeated clicks on the
same URL. Windows use almost all of Lab's width, leave its workspace tabs visible,
and cascade by 36 pixels vertically with a small horizontal offset so previous
title bars and close buttons remain visible. The cascade repeats every three
windows: the fourth starts at the first position again. Use each window's own
controls to activate, move or close it. Normal link opening uses the clicking device's browser
with no resource registry, confirmation, macOS helper or automatic window raising.

Use **+ Sublink** in a link's details to add destinations beneath it, such as
Google Docs tab URLs. Each sublink has its own title, URL, TL;DR and properties,
and can contain further sublinks. Hover over the parent sidebar link for one
second to reveal the indented hierarchy. Clicking a child opens its destination;
Cmd/Ctrl-click opens a browser tab. Secondary-click **Edit** opens that child's
own modal editor, including from its parent's Sublinks list. Child references can be pasted
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

Task branches can be promoted, nested or reordered by drag and drop, with their
terminal hierarchy following. Delete task requires two confirmations and the
exact task name. See [task moves and deletion](TASK-LIFECYCLE.md) for ownership,
source preservation and failure behavior.

The left task list opens task details on a normal click. Every pending subtask
and action item stays visible under its owner without hover or selection.
Selecting a task displays its assets beneath the list without hiding other
pending branches. Task details are not duplicated as a separate `Tasks.md` tree
in Unassigned. Secondary-click a task in the sidebar, its working header, or
the dashboard (including task history) to change its status.

Task terminals are optional. **Settings → workspace → Terminal sessions →
Each task gets its own terminal** is off by default and is saved for that
workspace across browsers. With it off, task clicks open details and activate
an existing linked terminal if its task passes the terminal status filter,
without creating a new one. With it on, Lab shows recommended task terminals
and creates or reuses the primary when selecting an eligible task. Explicit
**+ New → Current task** remains available in either mode and always creates a
fresh terminal of the requested type, even if the task already has a terminal.
Changing the setting preserves existing sessions. A task can have multiple
terminals with one primary: additional launches save their own task association
and appear as independent terminals, without a terminal parent. Clicking the
task still activates its primary; **Make primary** changes which one that is.
Promoting an independent member preserves the other terminals' task membership
and does not change their hierarchy. An ordinary terminal can be reassigned to
a different task, including across Objectives.
Refreshing or restoring task details does not spawn another terminal.

Task titles are hyperlinks to their required details document/subtab. Clicking
a title opens those details and enters task mode. Its working-area header keeps
the task's name, completion checkbox and **Edit task** visible while browsing
assets. Click the header's task name to return to details. Returning
to Tasks or switching objectives exits task mode. The red **×** in the working
area's upper-right corner closes task mode and returns to the task list. It
remains available while browsing native assets, follows the working viewport,
and stays above the native notebook toolbar. Navigation saves outgoing document
drafts. The Off/Semi/Focus feature has been removed; task selection no longer
adds focus-specific sidebar hiding or asset highlights.

Task Markdown opens in **View** mode with rendered, read-only content. Use the
**View · Edit** switch or **Cmd-click inside the task Markdown** to toggle the
native editor (Ctrl-click on other platforms). The shortcut preserves the draft
and saves pending edits when returning to View. Both modes share document
typography, heading sizes, column width,
links, quotes, code and table styling; View also keeps the editor's paragraph
spacing and text inset. View disables document Rename/Save/Revert/new-subtab
actions and the
task header's completion, icon changes and Edit task controls. Reading, links,
disclosures and View/Edit controls remain available. Edit returns to View after
three minutes without interaction with the document, header or its edit dialog;
pending edits save and remain visible, including drafts with a save conflict.
An open edit dialog locks its fields while preserving their values. Switching
tasks or reopening details starts in View again; edit permission is not stored.

Drag documents, document subtabs, notebooks, links, sublinks, files, folders or
worktrees onto a task row to attach references. Assets can also be dropped onto
the selected Task assets bucket or the task's asset-list dialog. Existing files
and Assistant documents are linked without copying content. Shared/worktree
scopes and original ownership remain unchanged. Duplicate drops keep one
association. The middle task-list asset button opens its attachments and can
detach optional assets; its mandatory details remain associated.

Task status badges show **⬜** for Undo with a red frame, **🚧** for
In progress, **✅** for Completed, **⏸** for Paused and **🚫** for Won’t do.
Secondary-click anywhere on the row to choose one of these five statuses. The menu
also opens with Shift+F10 and closes with Escape. Completed, Undo, Paused
and Won’t do update the task's subtasks too; In progress preserves them. Changing a
subtask updates its parent's aggregate status. Status is saved in the Objective
manifest and reflected in the task header and active tab. Recurring tasks carry
**🔄** in the sidebar and repeat badges. Terminal tabs show their icons instead
of task-status dots: 💻 for ordinary task terminals and ⏺ for children unless
a custom icon is selected. Status stays available in hover and accessible labels.
In the task dashboard, the right edge holds the icon used by its active tab and linked terminals.
Without a chosen asset, the right edge shows no icon. Its empty drop area
appears on hover or keyboard focus so an asset can still be dragged there.
Click the left status badge or right icon area to open **Task icon and terminal
color**. Distinct Objective asset icons appear first, alongside all built-in
service icons such as Jira, GitHub and Grafana. GitHub can be chosen even without
a GitHub asset. Suggested emojis follow, with a field for a custom emoji.
When the left sidebar folds into its icon rail, each task shows the chosen
custom icon or its default task status emoji. The compact icon opens the task;
expanding reveals titles and customization controls beside the same icon.
Task and subtask icons retain identical positions and sizes in both states;
recurring markers also stay in place. Headings, worktrees and pinned assets
above Tasks retain their height while folded. This also applies to the rest
of the first column: Files and Recently updated keep their full blank space
behind a single section icon, and META shortcuts keep their vertical positions.
Subtask titles are indented, with icons aligned in a fixed column. When a custom
icon is chosen, the sidebar shows it on the left and reveals the status badge
on the right. Both controls open the icon picker. Worktree title bullets stay
hidden while folded.
**Terminal text color…** opens the existing worktree palette. Preview the choices
and click **Save**, or cancel to retain the saved settings. **Default icon** and
**Default color** restore the defaults. Secondary-click retains the status menu.

Attaching assets and editing task details keep the chosen icon. Picking an asset
icon references it without attaching it. Dropping an asset onto the task's icon
area still chooses its icon and attaches it when necessary. The active tab and
linked terminals inherit the icon, including child, merged and recommended rows.
The chosen terminal text color applies to that task's terminal family, including
worktree names, without changing the worktree's own color or other tasks.
Existing saved asset icon choices remain valid.

The same settings are available through `lab objective apply --workspace ID
--file action.json`, with a `task-update` action:

```json
{"type":"task-update","objective_id":"OBJECTIVE_ID","task_id":"TASK_ID","icon":{"service":"github"},"terminal_color":"#58a6ff"}
```

Other icon values are `{"emoji":"💡"}` or
`{"asset":{"resource_id":"RESOURCE_ID"}}`; asset references may also target a
document tab, sublink or associated folder. `icon: null` clears a chosen icon,
and `terminal_color: null` clears the text override. Legacy `icon_asset_id` and
explicit asset-drop choices still work and replace a standalone icon choice.

## Documents, subtabs and notebooks

The Unassigned **+** creates Markdown documents or `.ipynb` files,
or links an existing workspace file. Owned documents support Rename and new
subtabs. Outside task mode, they open directly in the existing live Markdown editor:
click formatted text to edit it in place, type `/` for commands, or use the
editor's formatting shortcuts. **Save** and Cmd/Ctrl-S save immediately;
autosave runs after ten seconds without typing, and navigation saves the
outgoing draft. **Revert** loads the current saved version of that tab.
Unsaved drafts and editor undo remain available when switching between tabs.
Task-mode View/Edit switches preserve the same draft and editor undo.
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

Selecting a whole Objective in the top bar or sidebar also activates a terminal
assigned directly to that Objective. Keep the current terminal if it belongs
to the Objective; otherwise select the first available match. Task, subtask,
asset and worktree assignments do not count as whole-Objective assignments.
Clicking that terminal selects its Objective and opens the overview without
switching terminals again. Restoring a view or refreshing metadata does not
override the user's terminal selection.

**+ New** asks whether to open for the current workflow (workspace root), the
current Objective (its own directory), or a specific worktree in that Objective.
The worktree option opens a list restricted to that Objective's associated
checkouts. Workflow and Objective choices create a separate terminal on each
launch, even when their fixed main exists, and stay visible with task filtering
enabled. Objective choices save a whole-Objective terminal association;
worktree choices save a folder association. The Home demo offers the same
choices with simulated terminals. See [TERMINALS.md](TERMINALS.md#new-terminal-location).

The terminal selector always shows one fixed **🏠 workspace (workflow) main** at the top.
The fixed **🎯 Objective main** appears immediately after the active Objective's
divider and is labeled **Main**; inactive Objective mains stay hidden, including
in Show all mode. Named terminal rows show only their saved name, without extra
workspace, Objective, folder or **main** labels. Location markers keep their
color and full folder tooltip. Unnamed worktree terminals can use their worktree
as the fallback name.
These identifiers appear in compact and expanded lists, including dormant launch
rows. Other terminals keep the compact 💻 fallback or their task's custom icon.
Clicking a main row creates its session if needed and reuses it thereafter.
Default main and task launches start the configured workspace agent with Lab
context. Objective headers and dividers use their Objective color; ordinary
terminal names remain neutral. Worktree names keep their own assigned colors.
These tabs cannot be moved,
nested, renamed or reassigned through the tab controls. Existing extra
sessions remain ordinary terminals. Main roles are saved as
`main: "workflow"` or `main: "objective"` in the workspace terminal links;
workflow links have no Objective target.

By default, task tabs include In progress tasks and an explicitly selected Paused task,
plus children that inherit those contexts. Selecting a paused task reveals and
reuses its terminals; selecting another task or returning to Tasks/overview hides
them immediately. This also applies to `lab ui command task-open`. Selecting a
Not started, Completed or Won’t do task opens details without revealing, creating
or activating its terminal. Pausing the current working task hides its terminals
and parks its console immediately; click the paused task to show them again.
Active child families and merged tabs also respect this filter. Other sessions
keep running while hidden. Objective headers and the dropdown expand the same
current Objective. The **Show all** switch beside **Terminal** in the top panel
header reveals every task status in the active Objective and adds headers for
parked Objectives with saved sessions. Turn it off to restore In progress and
explicitly selected paused tasks. It remains visible when terminal names fold,
keeps keyboard focus and saves its setting in the browser. There is one shared
filter: separate Objective Show all / All shown buttons and their saved overrides
are removed. Notification clicks reveal only their exact destination temporarily
without turning the switch on.
Only the active Objective's terminals unfold in every filter mode. Clicking
another terminal Objective header selects that Objective, opens its terminals
and folds the previous group. Terminal settings control the same shared filter.

Task terminals show a left icon beside their title. A task with exactly one
assigned worktree uses that worktree's colored marker and name, including on
recommended terminals. Monochrome custom icons such as GitHub follow the name's
color; an explicit task terminal color overrides the name and icon while retaining
the worktree marker. Ordinary task terminals use 💻 and children use ⏺ when no
custom icon is configured. Terminal tabs omit task-status and yellow activity
dots; status names remain in hover and accessible labels, and green result review
remains available. The sidebar keeps its task status controls.

The vertical terminal rail keeps the same icon sizes, row heights and marker
and green review positions when hovering to reveal titles. Hierarchy relationships
and disclosure remain intact without shifting the icon column.
The renewal (**↻**) button is shown beside visible terminal titles and hidden
when titles are folded. Custom task icons and default emojis remain visible.

Task terminals follow sidebar task/subtask order as invisible contiguous blocks.
Drag a task title above or below another task to move its complete branch and
terminal blocks. Alt-drag offers nesting options. Terminal tabs reorder only
within their own task's block, individually, without changing task ownership or
parent context. Saved internal order survives task moves and reloads. Task-bound
terminals appear as individual rows, including inherited children and automation
members; their context, process, checkout and agent conversation are preserved.
Generic terminals retain **Move below**, **Make child**, **Cancel** and parent
hover/focus disclosure. **+ New → Launch automation…** still requires an In
progress task and assigns its first terminal as that task's primary. Pausing
the chosen task hides the complete task block.

Task completion records `completed_at` as Unix seconds in the Objective
manifest. Pausing, reopening or declining clears it. **Clean up completed /
inactive terminals** opens the reviewed Resources cleanup list. A completed-task
terminal qualifies after 24 hours, with no activity or access during the last
24 hours. Fixed mains, connected sessions and working/waiting agents are kept.
Legacy completed tasks without a timestamp are not expired based on an invented
completion date. Other sessions retain the seven-day inactivity rule.

Drop the Objective name onto a terminal name, or a terminal onto the sidebar's
Objective name, to make that ordinary session the Objective main. Clicking that terminal
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

Asset links are separate from workspace/Objective/task ownership. Use a terminal's
**Link to asset…** picker or an asset's **Link to active terminal** action; these
also work with fixed main terminals. Asset drops use the same independent link.
The terminal keeps its primary role, task visibility and launch folder. Clicking
the asset activates its terminal, and clicking the terminal opens that exact
asset, including document subtabs and URL sublinks. Its tab and active header
adopt the asset's icon before task/default icons. **Unlink asset** clears only
the asset association. Task and whole-Objective drops still assign ownership.

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
terminal to the task if it has no existing task. The reverse terminal-to-task-row
drop also works for unassigned terminals in the left column. Task-bound terminals
keep their existing block. Clicking the terminal opens the task's details in Focus mode. Its launch folder, process
and original Assistant ownership remain intact.
Assigning an unassigned terminal to a task or subtask also renames its display label to
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
Terminal mappings use stable session UUIDs. Their existing task, Objective,
workflow/main and view fields retain terminal ownership. A separate optional
`asset` target holds its own `objective_id` and a resource/subtab/sublink, file or
folder. Apply `{"type":"terminal-asset","session_id":"UUID",
"objective_id":"ID","resource_id":"ASSET_ID"}` to link one, optionally adding
`tab_id` or `sub_link_id`. Use `{"type":"terminal-asset","session_id":"UUID",
"unlink":true}` to remove it. The same action is available through
`lab objective apply --workspace ID --file /absolute/action.json` or
`POST /api/objectives`; it preserves the terminal's original ownership.
External link
details use optional `tldr`, `metadata` and nested `sublinks` fields. Sublinks
have stable IDs; terminal mappings use `sub_link_id` to retain the exact target.
Legacy terminal mappings retain their parent fallback when a sublink is removed;
new asset bindings stop navigating when their exact asset no longer exists.
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
middle task view. Selecting a task reveals that task's subtasks; selecting
another collapses the previous group. The live workspace also keeps In progress
subtasks visible under every parent. The live list reserves space for these
permanent rows plus the largest additional subtask group; the demo reserves its
largest group, so **Task assets** stays at the
same position while navigating tasks, subtasks or closing task mode. Task mode keeps the task's name, icon,
completion control and red corner close visible while browsing its assets.
Click the task name in that header to return to its details.

Drag an asset onto any task row to attach it. Drop it into Objective to pin it
as shared context. The **⋯** on an asset also chooses its bucket and task.
Every asset and individual document subtab has a **☆/★** control that toggles
shared Objective context without removing its task associations. Drop an
asset onto a task's icon area to select that icon and attach the asset if
needed. Tasks default to ⬜ / 🚧 / ✅, and the current tab and linked terminal inherit the
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
state and simulated terminals separate from workspace data. The header's explicit
resource trials open real URLs and compare a pop-out over Lab, an embedded panel,
and a normal browser tab. The pop-out trial uses Lab's shared opening behavior,
including almost full width and the three-position cascade.
Chrome controls the window frame; these remain ordinary native windows.
