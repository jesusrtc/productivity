# Terminal transport

Lab terminals are persistent tmux sessions bridged to the browser through a
PTY and WebSocket. The browser's input/output path is unchanged by socket
rotation: once attached, terminal bytes continue to travel directly between
the PTY and WebSocket event loop.

## New terminal location

Opening a new terminal in an Objectives workspace asks where it should start.
Workflow and Objective choices create additional sessions without replacing
their fixed mains. Default main/task launches use the configured agent, with
Lab context supplied at startup. **Terminal** explicitly creates a plain shell.

- **Current workflow** opens at the active workspace root.
- **Current task** creates a fresh session of the selected shell or agent type
  in the task's launch folder. A task can have multiple terminals: its first
  terminal becomes primary, and later explicit **+ New** launches belong directly
  to the same task as independent terminals. The primary keeps running and
  remains the terminal activated by task navigation, including when it came
  from an automation. **Make primary** can promote a new terminal later.
- **Current Objective** opens in the Objective's directory and saves a whole
  Objective association in that Objective's terminal tabs.
- **Specific worktree** opens a second list containing only that Objective's
  associated worktrees and folders. Choosing one uses its exact checkout and
  saves its folder association.

These choices save the new terminal's own workspace, Objective or task context;
they do not make it a child of the active terminal. Task membership survives a
reload without browser hierarchy state. Explicit **New subterminal**, automation
groups and deliberate nesting keep their separate child-terminal behavior.

For CLI/API task association, the `terminal` Objective action accepts `task_id`
and `primary: false` to add an independent member while retaining the primary.
The first member becomes primary automatically. Omitting `primary` or setting it
to `true` promotes that terminal; all other members retain their task association.
Use `lab objective apply` or `lab api call POST /api/objectives` for this action.

The chooser applies to shell and agent terminals, including file-created
terminals and the first automatic launch. Cancel or switching workspace,
vault or Objective starts nothing. Worktree changes also cancel stale choices.
The launch folder stays fixed, and restoring an existing terminal keeps its
original folder without asking again. Workspaces without Objectives retain
the workspace-root and pinned-folder chooser.

## Objective sections

The **Show all** switch sits beside **Terminal** in the top panel header, above
the terminal tabs. On reveals every task status; off shows In progress tasks and
explicitly selected paused tasks, along with generic workspace/Objective
terminals. It stays visible when terminal names fold. Mouse, Space and Enter
toggle it, with its current on/off state exposed to assistive technology.
The setting is saved in the browser and synchronized with Terminal settings.
Separate per-Objective Show all / All shown buttons and their saved overrides
are removed. The switch does not select a task or start or stop any session.

Only the active Objective's terminal section unfolds. Other Objective headers
remain available as navigation: click one to select it, show its terminals and
fold the previous section. This also applies while **Show all terminals** is
enabled; that setting reveals task statuses without expanding other Objectives.
Folding preserves running sessions and their saved child-terminal layouts.

The Objective main is labeled **Main**. Named terminal tabs display the saved
name alone, without workspace, folder or **main** text beside it. This also
applies to named worktree terminals and legacy merged tabs. Colored location
markers retain full folder details in their tooltips. Unnamed worktree terminals
can still use the worktree as their fallback name.

Task terminals form invisible contiguous blocks in sidebar task/subtask order.
All members of one task stay together, including directly assigned terminals,
inherited children and automation members. Drag a task title above or below
another task to move the whole branch and its terminal blocks. Alt-drag offers
nesting options; the **Tasks** header promotes a dragged task to the top level.

A terminal tab may move individually before or after another terminal in the
same task's block. It cannot leave that block, move its task, or change task
ownership through a drag. Cross-task, divider and empty-rail drops are rejected.
Task-bound members render as individual rows so nested task terminals cannot
split another task's block. Their real parent relationships remain available
for context, appearance, recovery and primary selection. Generic terminals
retain their existing child disclosure and placement menu. Saved order inside
a task persists across task moves and reloads; identities, processes, launch
folders and conversations are preserved.

During a tab drag, neighbours slide smoothly around a preview matching the
dragged tab's size. The same feedback appears in the workspace tab bar and in
vertical or horizontal terminal lists. Moving back and forth retargets the
animation from the current visible position. Hover never saves tab order or
changes task ownership; dropping applies the final valid preview, while leaving
or cancelling restores the original layout. Invalid task-block targets show no
placement gap. Reduced-motion preferences keep the gap and omit the sliding.

## Notification navigation

Red attention and green finished cards open the exact reporting terminal,
including its owning workspace, Objective, task and linked asset. Each click
still checks the live session incarnation before activation or green review.
The destination tab scrolls into view and pulses; red requests remain visible.

The **bell and switch** beside **Lid Awake** opens history in the same
floating stack. It lists the latest observed red/green alert per running terminal,
including reviewed and superseded alerts, by creation time descending. Start
with 20 and use **Load more** for another 20. The latest alert is retained in
the session-local `@lab_notification` option and travels in the existing batched
listing, including when the browser was closed. Browser storage also retains
observed alerts from older CLI versions. Alerts are deduplicated across shared
views and tied to the exact tmux incarnation. Recreated or stopped sessions do not
inherit another session's history. Reports replaced before history retention
was installed are unavailable.

The stack and center are anchored to the bottom right without reserving console
space. The center's search field stays at the top while results scroll. Search
matches all entered keywords across workspace, Objective, terminal, vault,
status, creation time and message, ignoring case and diacritics. It filters the
complete history before the 20-item pagination, including reviewed alerts.
Typing, background refresh and reviewing a card preserve the field and caret.
The result count and no-match message update as you type. **Clear search** resets
the page and keeps focus in the field. Closing clears the filter and restores
the unfiltered active-alert stack. Use `lab ui inspect` and `lab ui fill` on the
**Search notifications** field to search through the same UI.

The control has no visible label and exposes **Show all notifications** to
assistive technology. The terminal icon precedes workspace and Objective names
in each card header, followed by the terminal and vault. Task, linked-asset and
automation icons use the native owner's saved choices, including inheritance.
The batch reads owner metadata once per workspace,
including parent inheritance and shared terminals, without loading document
bodies or transcripts. A white vertical line marks active alerts and turns off
when their status resolves or a finish is reviewed.

Notification navigation, status events and polling keep history and its bell
switch open, allowing consecutive card checks. Outside click, the switch, close
and Escape return to the active-alert stack. Dismissal never acknowledges a
finish. A historical finish is reviewed only if it is still the exact current
report; newer reports and working/attention indicators remain intact. The
`terminal-notifications` UI command accepts `history: true`, and
`terminal-notification-center` accepts `open: true|false` through `lab ui`.

For notification arrivals, the terminal connects at its fitted size and paints
output using its DOM renderer first. Graphics atlas and shader initialization
run after the first output paint in browser idle time, so they do not block
activation. Cached panes use the same deferred graphics handoff. Input, output,
focus and the terminal buffer are retained, with the existing DOM fallback on
graphics failure. Parking, removing or switching away from a pane cancels its
pending initialization. The local click-to-visible-terminal target is below
200 ms; ordinary terminal-tab activation keeps its existing renderer policy.

In a source checkout with Lab running and an existing Home notification, run
`core/.venv/bin/python scripts/perf/lab_notification_latency.py` from the checkout
root. The probe clicks real cards in three disposable Chrome profiles and keeps
all samples, including uncached first opens. It checks the exact session, visible
output and keyboard focus after a paint opportunity. It sends no terminal input,
disables automatic session creation in its profiles and leaves the user's browser
review state untouched. `--output /absolute/path/results.json` retains the timings.
Add `--history` to check consecutive card clicks with **Show all** kept on.

## Terminal automations

Closing a parent tab confirms deletion of its full terminal family before
stopping anything. The question includes the number of child terminals, counting
folded children and nested descendants. Confirming deletes children before the
parent, purges their saved sessions and removes their browser layout entries;
Cancel preserves them all. Automation groups, ordinary subterminals and merged
parent tabs follow the same rule. Closing a child with descendants affects its
own branch. Attached external sessions are detached from Lab. Failed deletions
are reported, and successful closes remain removed. Use **Close tab** in the
terminal menu or the current-terminal close action; `lab ui` exposes the same
confirmation, with `--confirm yes` to approve it.

Configure saved command groups in **Settings → workspace → Terminal automations**.
The workspace's **Terminal sessions** section also has a shortcut. Each automation
has a name and an ordered list of terminals, each with a terminal name,
working directory and shell command. Each terminal can also have optional guidelines:
labeled notes or commands shown above its console, beside the request history.
Use **Copy** to copy an entry and paste it into the terminal yourself. Guidelines
are never executed by launching or relaunching the automation. For example, save
`ssh my-project` as the launch command, then add separate guidelines for starting
the app normally or with a debugger. Add, edit, reorder or remove entries, then
save. Saving and opening settings never launch commands.

Each automation has **Icon and text color** controls, with a terminal-outline
icon like a command window, built-in service icons including GitHub, suggested
or custom emoji, and uploaded PNG icons (up to 256 × 256 pixels and 64 KB).
The main defaults to green text with a matching monochrome icon. In every
terminal’s controls, **Inherit main icon** is the default; child text defaults
to the theme’s primary color (white in dark mode). Set an icon or text color
on a terminal to override that default. Standalone launches use the first
terminal’s name for their main; launching beneath an existing terminal keeps
that parent’s name and applies the automation’s main icon/color to it.
An explicit first-terminal icon becomes the inherited icon for its standalone
children. Ordinary new children also inherit an automation parent’s icon.

The launch preview shows each effective icon and color. Appearance is retained
in saved terminal metadata and recovery history, independent of commands and
task colors, so browser reloads and explicit recovery preserve it. Selecting an
icon never changes the terminal’s task, folder or linked asset. Recipe fields
`icon` and `color` configure the main; each `steps[]` entry accepts the same
optional overrides. Use `{"builtin":"terminal"}`, `{"service":"github"}`,
`{"emoji":"🚀"}` or `{"image":"data:image/png;base64,…"}` for `icon`; colors
use `#RRGGBB`. A null step icon inherits and a null step color uses the default.
Inspect or save them through the existing `lab api` automation endpoints.

Choose **+ New → Launch automation…** and choose an **In progress task** to create
a group. The picker lists WIP tasks across this workspace with their Objective
names and preselects the current WIP task. Launch is disabled until a task is
chosen; with no WIP tasks, set one to In progress and reopen the launcher.
The first defined terminal becomes the task's primary automatically, and the
remaining terminals become its children in definition order. No starter terminal
is needed. If the task had a primary, its session keeps running while the new
first terminal takes ownership. Every new run requires a WIP task, including
launches from the workspace or an existing generic terminal.

The picker lists this workspace's saved groups and previews every command with
its resolved directory before **Launch**, marking the first step **Primary**.
Its **Configure automations** button opens the same workspace settings.
Secondary-click a terminal, including a fixed workspace or Objective main, and
choose **Launch automation…** to choose a WIP task and nest the first automation
row beneath that terminal, with the remaining steps beneath the first row.

An empty directory uses the chosen task's Objective folder.
When launched from a terminal, it uses that parent's fixed launch folder instead.
Relative paths resolve against the same base folder for every step; absolute
paths and `~/folder` are also supported.
Every directory is checked before any command starts. Commands start in list
order in separate tmux sessions, with **5 seconds between launches** by default.
Set **Seconds between launches** in the automation's workspace settings to
change this interval (0–300 seconds, including fractions); 0 disables waiting.
Existing definitions without this field also use 5 seconds. The first command
starts immediately, with no extra wait after the last. The launch preview shows
the saved delay. Commands run independently. For dependent operations,
combine them in one command, for example `npm run build && npm run dev`.
An exited command prints its exit code and leaves an interactive shell with the
logs retained. Automation tabs show their saved names with the configured icon,
inherited by default by their children. Older running sessions without appearance
metadata keep their task/default icons until a new configured launch. Ordinary
task terminals use 💻. A single centered status dot
sits between icon and name; location dots and Home/main badges are omitted.
Agent-reported status uses steady yellow for working, pulsing red
for attention and blinking green for finished; task-status dots remain omitted.
Floating cards at the bottom right show red input requests until status changes
and green finished messages until reviewed by click or replaced by a newer status.
Clicking a message opens the owning workspace, Objective and exact terminal,
scrolls its tab into view and pulses it three times (a steady highlight with
reduced motion). Collapsed groups and the selected Objective's task filter open
when needed to reveal that tab. Only a green click reviews and clears status.
Notification and terminal-tab clicks both select the owning task/subtask and
open its linked asset within that task, or its details when no asset is linked.
Task assets stay accessible, including for secondary and inherited child
terminals. Explicit task ownership takes priority over an asset in a different
Objective.
Green messages have no timer and persist across reloads.
Messages are deduplicated across shared views, and red takes precedence in
workspace, Home and Assistant indicators.
The cards overlay the interface and remain visible with the terminal panel closed.
Only green clears on a tab click. LLM-controlled terminals also turn yellow
immediately on submitted input; the next agent report supplies the real WIP text.
`lab context llm` loads instructions and marks manual agent sessions;
`lab terminal llm --off` restores shell behavior.
Hover shows LLM control, the report and reveals names
without moving or resizing icons and controls. See
[terminal status](terminal-completion.md) for commands and lifecycle rules. An active
child stays visible along with its direct siblings and parent/grandparent path.
Other automation children appear after holding the pointer over their parent
for one second. Moving away cancels the reveal. Keyboard disclosure is immediate,
and background tab refreshes preserve the elapsed hover time.
When names are visible, each parent also has a small arrow button. Click
**Keep child terminals expanded** to keep its children visible after leaving
the rail, refreshing the list or reloading the page. The arrow is highlighted
while pinned; click **Collapse child terminals** to return to temporary hover
disclosure. Each parent's choice is saved per workspace/vault in this browser.
Nested and automation parents use the same control. It is hidden in the compact
icon rail and supports Enter/Space without selecting or relaunching a terminal.
Active-family and own-In-progress rows keep their existing visibility rules.
Through `lab ui inspect` / `lab ui click`, target the parent's `[data-subtab-pin]`.
A stopped automation adds a **↻**
relaunch button beside its tab. Its parent gets the same control to relaunch all
stopped descendants together; running or unknown children are skipped.

Recovery follows the launched foreground process, SSH connection or tmux client.
An idle shell after that command exits, a detached nested tmux client, or a missing
terminal session makes recovery available. A browser disconnect alone does not.
Reattaching a nested tmux client uses the original command, allowing an existing
inner session to keep running. Apps started manually inside a live SSH connection
are not individually monitored. Multiple panes/windows and unavailable process
status leave recovery disabled. Lab checks again immediately before replacing an
idle pane, keeps its tab identity and saves previous output under
`.lab/terminal-automation-logs/`. Repeat clicks cannot replay the same launch.
The **Renew connections** control on a merged parent tab explicitly reruns all
eligible child automations, including running connections. It keeps their session
identities, archives previous output, and leaves the parent console untouched.
The same single-pane ownership and launch-generation checks apply.

If the launch command returns while a background service keeps running, configure
the child's optional **Background service check**. This check runs in the original
working directory: exit 0 means running, exit 1 means stopped, and other failures
or a timeout mean unknown. It is only used when no foreground process remains.

The automation's first row owns the chosen task; its children inherit that task
even when launched beneath a generic workspace or Objective main. Existing parent
ownership is preserved. Pausing the task hides the entire automation group and
parks its console immediately. Explicitly select that paused task to inspect
its terminals, then leave it to hide them again.
Task children follow the usual WIP/selected-task filter and the same parent-hover
disclosure. An automation primary with its own In progress task remains visible
like other task primaries. The fixed main itself remains a root. A launch selects
the first defined terminal unless the user has navigated to another task or workspace.

Agents can use the same menu through `lab ui inspect` and `lab ui click`, or call
`lab api call POST /api/term/automations/launch --body-file /absolute/launch.json`.
Inspect its schema with `lab api describe POST /api/term/automations/launch`.
Both modes require `workspace_id`, `automation_id`, the saved catalog `revision`,
and a fresh UUID `run_id` (plus `vault` when needed). Both `objective_id` and
`task_id` are required and must identify an In progress task. Preview and actual
launch both validate this, including when a previewed task has since been paused.
To create a new group, omit `parent` and optionally
override the base folder with `cwd`. To add children to an existing terminal,
pass its runtime `parent` name alongside the task fields and omit `cwd`. `preview: true`
checks all directories without starting sessions. Task ownership is persisted
by the API; tab order and child nesting belong to the browser that launched it.
The preview includes `launch_delay_seconds`. To configure it through the CLI,
read the catalog, set that field on the chosen automation and save the catalog
with its revision through `POST /api/term/automations`; use `lab api describe`
to inspect the schema. Launch requests use that saved delay. Increase
`lab api call --timeout` for runs whose combined waits exceed its 30-second
default (for example `--timeout 180`). Settings reads and saves remain available
while a run waits. Repeated requests adopting already-running terminals do not
add waits or replay commands.

Definitions live in the workspace's `.lab/terminal-automations.json`, so every
browser sees the same saved recipes. This is separate from browser-owned tab
appearance and hierarchy. Saves reject stale revisions rather than overwriting
another settings edit. Repeating the same launch request adopts its children;
an explicit later launch starts a new group. If a later child fails to spawn,
earlier children remain running and the picker reports the failure. Restoring a
stopped terminal opens a shell without automatically replaying its command.
Original commands and launch-time guidelines are kept privately in
`.lab/terminal-automation-runs.json` for explicit recovery and merged-tab renewal;
passive refresh, browser reconnect and status polling never replay them.

## Terminal tab names

Vertical tabs show a flat icon rail with worktree and green review markers.
A saved custom task icon takes precedence over the 💻 task or ⏺ child fallback,
including on recommended task terminals and inherited children. Monochrome
icons such as GitHub follow the title's custom or assigned worktree color.
Merged tabs use the parent's icon while retaining activity from the selected
child's actual console. Compact horizontal tabs use the same icons and corner
markers. Hover reveals names immediately beside the existing vertical icons;
their size, row heights, markers and green review controls remain fixed.
The renewal (**↻**) button appears beside the title only while titles are
visible; collapsing the rail hides renewal while keeping its emojis and custom
icons visible. Leaving after a brief hover hides the names again. Clicking
the rail or hovering for 3 seconds keeps the names open while moving to Files
or other views; clicking inside the terminal console hides them. Escape also
closes the names for keyboard navigation. The expanded list overlays the
console, preserving its text width, and its right border adjusts the name width.
Clicks on the expanded list, scrollbar and width divider belong to the tabs,
including the portion covering the console. Only the exposed console receives
terminal clicks.

Set **Keep tab names open after hovering (seconds)** in
**Settings → Global → Terminal appearance** to change the delay. The default
is 3 seconds; zero keeps names open immediately on hover. This preference is
saved in the current browser. Horizontal tabs retain their normal layout.

The first column uses the same hover delay and opens over the working area.
Its collapsed Files and Recently updated sections each show one icon for the
whole list. Expanding restores every file and filter; clicking the main working
area or terminal console returns it to the compact rail.

Secondary-click a child terminal and choose **Make primary** to promote it to
its immediate parent's position. The previous primary and its other children
move beneath the new primary; ancestors retain their positions. Each terminal
keeps its own console, asset link, icon, saved label and launch folder. Nothing
is restarted. Selecting the previous primary's **Make primary** switches back.

For independent members of the same task, **Make primary** only changes which
terminal task navigation opens. Both remain independent, with their own task
associations and unchanged terminal hierarchy.

When the parent owns a task or workspace/Objective main role, that ownership
transfers through the shared Objective API and task clicks activate the new
primary. A terminal already assigned as a separate task's primary cannot take
another primary role through this menu. Browser tab hierarchy and ordering
remain saved per workspace and vault. The menu is also available through
`lab ui contextmenu` and `lab ui click`.

Earlier merged tabs remain readable. **Make primary** separates them and
promotes their selected child, or **Show separate terminals** only restores the
original rows. Until separated, **Open parent terminal** retains access to the
original console and **Renew connections** keeps its explicit batch behavior.

## Request history

Click **Requests** above the terminal to open its submitted-message history.
When the strip shows an AI **Objective**, that label opens the same history.
Each request has a three-line preview; click it to unfold the full message.
The modal stays with the terminal it was opened for and updates while open,
preserving unfolded requests and the position of older requests you are reading.

Accepted messages come from Claude, Codex and Copilot conversation logs,
including pasted or edited multiline input. Enter triggers a refresh; drafts
and shell input are not stored as requests. Submitted `/clear` and `/new`
commands create dividers, and detected conversation changes show **Session
refreshed**. Previous requests remain available after a clear or browser reload.

History is retained in `$LAB_HOME/terminal-requests.sqlite3` (normally
`~/.lab/terminal-requests.sqlite3`), keyed by the physical terminal name. The
history API uses the same workspace/vault access checks as the terminal list.
Existing messages in the current provider transcript are imported; prior
conversations remain available once Lab has observed them. Transcripts are
read incrementally without sending commands or changing the agent session.

## Sidebar references and object links

Sidebar objects dropped inside the console paste a shell-quoted reference
without Enter: the captured absolute file/folder path, document path with its
subtab fragment, or external URL. Objective Tasks also has a draggable reference.
In an Objectives workspace, dropping an asset onto a terminal's name instead
stores an independent navigation link. A terminal's workspace, Objective or task
ownership still controls its launch folder and visibility. The asset link does
not replace that ownership, including for fixed mains and automation primaries.

Use the terminal menu's **Link to asset…** picker, the asset menu's **Link to
active terminal**, or drag an ordinary terminal onto a left-column asset.
Clicking either side activates the other: notebooks/files open their normal
viewer, document subtabs retain their IDs, and URL links open their exact
destination through the usual browser action. The tab and active header use the
asset's shared icon, ahead of task/default icons; the terminal name stays intact.
When the terminal has no explicit or inherited task, the linked asset's unique
task assignment supplies its navigation context without reassigning the session.
Exact subtab/sublink assignments take priority over whole-resource assignments.
If several tasks share the asset, retain an already selected matching task;
otherwise open the asset without guessing a task. Linked folders open without
entering the separate worktree-browsing mode when a task is selected.
**Unlink asset** restores the usual icon without stopping or restarting anything.
New file links outside Objectives also activate in both directions without
requiring **Sync linked**; existing links retain that preference until relinked.
Task/Objective drops can assign unassigned terminals. Task-bound terminals
retain their membership; asset links remain separate. See [OBJECTIVES.md](OBJECTIVES.md).

## Inactive terminal cleanup

Task retention runs automatically every minute across registered vaults, without
an open browser. Completed, Won’t do and Undo/Not started tasks retain running
terminals for one hour after their status changes; Paused retains them for three
days. The default bar hides inactive task terminals except while their Paused
task is selected. Leaving that task hides its terminals and inherited children
immediately, even when its console was active. Selecting it reuses the existing
terminal; the workspace task-terminal setting still controls missing-session
creation. Notification navigation temporarily reveals only its exact destination
without saving Show all. Explicit Show all remains available during that window.
A return to In progress cancels cleanup;
each different status starts a fresh window. Repeated saves of the same status
do not extend it. Children inherit their saved parent’s task unless they have
their own task assignment. Automation launches persist this relationship even
from the CLI; existing browser hierarchies are copied when their bar is opened.

The worker rechecks task ownership/status under the task lock and atomically
matches the exact tmux socket, session ID, creation time and pane PID before
stopping anything. Unlike idle cleanup below, task expiry also stops connected
and busy inactive-task processes. Main terminals, managed server tabs, unrelated
terminals and shared document processes are excluded. Saved conversation IDs,
task links and parent ownership are retained; a retirement marker prevents
automatic browser restoration. Explicitly reopening a terminal clears it.
Missing historical status timestamps get a full grace period starting on first
observation, persisted at the vault’s `.lab/state/task-terminal-retention.json`.
The effective window cannot begin before that tmux incarnation was created.

`GET /api/term/task-cleanup` reports the policy, pending expirations and last run;
`POST /api/term/task-cleanup` runs a check immediately. Both require admin access
and are available through `lab api call`. `POST /api/term/sessions/parents` saves
cleanup inheritance for the specified workspace/vault without changing another
browser’s layout. Assistant-linked tasks map Not started to Undo, Done to
Completed, Skipped/Cancelled to Won’t do and Blocked to Paused. The configured
Assistant database remains the only eligible Assistant source. Set
`LAB_TASK_TERMINAL_CLEANUP=0` to disable automatic checks.

Open **Resources** in the header and choose **Show cleanup candidates**. The
Resources table shows sessions with no recorded activity/access for more than
seven days, initially across **All workspaces**. Tabs narrow the review to one
workspace, including workspaces with no eligible sessions. Arrow keys and
Home/End navigate the tabs. **Show all processes** restores resource monitoring.

The bulk kill button applies only to the displayed candidates; each row also
has an individual Kill button.
Confirmation shows the exact session names; the server rechecks their identity
and inactivity before stopping them. Connected terminals, working/waiting
agents and managed servers are excluded. Saved conversations remain available.

## Workspace renames and session identity

Rename a workspace from the secondary-click menu on either its vault row or
its top-level tab, or run `lab workspace rename <id> "New Named Workspace"`.
The folder becomes `workspaces/new-named-workspace`. Lab updates its own saved
paths, terminal links, and tab state. A conflicting destination is rejected.
An executing notebook must finish before its folder can move.

The workspace's internal ID stays fixed. `.lab/state/workspace-locations.json`
maps that ID to its current directory and can be rebuilt from workspace metadata.
Each terminal has a separate UUID, saved in the workspace's session list and
indexed in `.lab/state/session-index.json`. New tmux names use
`neurona-<uuidhex>`; display labels and workspace folder names do not determine
terminal identity. Neither a workspace rename nor a tab-label change creates
a replacement terminal.

Existing live sessions keep their transport names and sockets, and are adopted
into the UUID index without interruption. When later recreated, they use their
UUID transport name. Agent resume IDs remain separate and unchanged.

Lab repairs nested Git worktree links during a move. It does not rewrite
absolute paths embedded in user scripts, virtual-environment launchers, or a
running program's private state; those may need updating after a folder rename.

### Migration regression checks

Run `make test-all` for the CLI, backend, frontend behavior, latency, and
reconnect suites, then `make check-ui` for the running application's Chrome
smoke check. The focused migration tests are in
`core/tests/test_workspace_rename.py`: folder moves, cross-vault isolation,
collision rejection, rollback, Git worktree repair, missing-index recovery,
legacy-session adoption, repeated renames, stale notebook writes, deletion,
and UUID isolation when a deleted workspace ID is reused. They also launch a
real notebook kernel and a real tmux process on a disposable socket to verify
that variables, process identity, and working directories survive the move.

## Rolling socket rotation

macOS security and keychain context is captured by a long-lived tmux server
when that server starts. If a repaired client identity is visible in a fresh
iTerm process but not in existing Lab terminals, seed a new Lab tmux socket
from that working iTerm:

```bash
lab terminal rotate
```

Run the command directly in iTerm, not from inside tmux or a Lab terminal.
Lab then routes newly created terminals, Copilot sessions, managed workspace
servers, and proxy control sessions to the new socket. Existing sessions stay
attached to the previous socket and continue running without interruption.

To move only Copilot to the fresh security context, close its existing Lab
terminal tab and reopen it after the rotation. Other open terminal tabs do not
need to be restarted.

Inspect the current generations with:

```bash
lab terminal status
```

Rows are labeled `active` or `draining` and include the number of Lab
sessions on each socket. Attach commands returned by the API and UI include
`tmux -L <socket>` when a session is on a named socket.

## Attach an existing tmux session

Open **+ New**, paste an existing tmux session name into **Attach tmux
session**, and select **Attach**. Lab searches the active and draining socket
generations and creates a lightweight grouped-session alias inside the current
workspace. The alias shares the source session's windows and panes; it does not
start a nested tmux client or forwarding process.

Closing an attached Lab tab removes only this alias. The original tmux session
continues running. Attached aliases are not automatically recreated as plain
shells if the source later disappears; paste the source name again to reattach.
For access safety, importing a host tmux session that Lab does not already own
requires an administrator account.

## Resource and UX guarantees

- Steady state uses exactly one routed tmux server.
- During a handoff, routing is bounded to one active plus one draining server.
  A second rotation is refused until the old generation has drained.
- The draining route is removed automatically when its last Lab session
  closes. There is no keeper shell, watcher thread, polling daemon, or
  per-terminal helper process.
- The active named tmux server uses `exit-empty off` so its macOS security
  context remains available between terminal launches. This is one small,
  idle tmux process when no Lab sessions are open, not an accumulating pool.
- Session listing performs one tmux lookup in steady state and temporarily two
  during a drain. Keystrokes, output, scrolling, resizing, and reconnects do
  not perform socket discovery.
- Existing default-socket commands retain their original argv shape, so
  installations that never rotate behave exactly as before.

If the active named server exits unexpectedly, Lab does not silently recreate
it from the backend's older security context. New-session requests return a
clear error; run `lab terminal rotate` again from the working iTerm. Existing
sessions on any still-draining socket remain available.

The global routing file is `$LAB_HOME/tmux-sockets.json` (normally
`~/.lab/tmux-sockets.json`). It is atomically replaced and normalized to at
most two generations. Do not edit it by hand; use `lab terminal`.

## Framework context in agent terminals

New Claude, Codex, and Copilot terminals use `lab agents run` to add the
short instruction to run `lab context llm`, which loads the full agent guide,
user guide, per-terminal changelog differences and owning instruction paths, and marks the terminal
LLM-controlled. Each workspace retains its own instructions.
The wrapper execs the agent; no persistent helper process or workspace agent
files are created. Plain shell tabs and attached sessions are unchanged.
See [Agent context](AGENT-CONTEXT.md) for manual launches and legacy-link cleanup.
