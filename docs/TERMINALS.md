# Terminal transport

Lab terminals are persistent tmux sessions bridged to the browser through a
PTY and WebSocket. The browser's input/output path is unchanged by socket
rotation: once attached, terminal bytes continue to travel directly between
the PTY and WebSocket event loop.

## New terminal location

Opening a new terminal in an Objectives workspace asks where it should start:

- **Current workflow** opens at the active workspace root.
- **Current Objective** opens in the Objective's directory and saves a whole
  Objective association, placing it at the top of that Objective's terminal tabs.
- **Specific worktree** opens a second list containing only that Objective's
  associated worktrees and folders. Choosing one uses its exact checkout and
  saves its folder association.

The chooser applies to shell and agent terminals, including file-created
terminals and the first automatic launch. Cancel or switching workspace,
vault or Objective starts nothing. Worktree changes also cancel stale choices.
The launch folder stays fixed, and restoring an existing terminal keeps its
original folder without asking again. Workspaces without Objectives retain
the workspace-root and pinned-folder chooser.

## Terminal automations

Configure saved command groups in **Settings → workspace → Terminal automations**.
The workspace's **Terminal sessions** section also has a shortcut. Each automation
has a name and an ordered list of child terminals, each with a terminal name,
working directory and shell command. Each child can also have optional guidelines:
labeled notes or commands shown above its console, beside the request history.
Use **Copy** to copy an entry and paste it into the terminal yourself. Guidelines
are never executed by launching or relaunching the automation. For example, save
`ssh my-project` as the launch command, then add separate guidelines for starting
the app normally or with a debugger. Add, edit, reorder or remove entries, then
save. Saving and opening settings never launch commands.

Secondary-click a terminal, including a fixed workspace or Objective main, and
choose **Launch automation…**. The picker lists this workspace's saved groups and
previews every command with its resolved directory before **Launch**. Its
**Configure automations** button opens the same workspace settings.

An empty directory uses the parent terminal's fixed launch folder. Relative paths
resolve against that folder; absolute paths and `~/folder` are also supported.
Every directory is checked before any command starts. Commands start in list
order in separate tmux sessions and run independently. For dependent operations,
combine them in one command, for example `npm run build && npm run dev`.
An exited command prints its exit code and leaves an interactive shell with the
logs retained. Expanded automation tabs show only their saved names in white,
without icons, status badges or folder captions. The folded rail shows one white
bullet per automation terminal, with names revealed on expansion. Child-tab hover
expansion and terminal controls still apply. Automation children appear only
while hovering over their parent or using keyboard disclosure, even when active
or inheriting a WIP task. A stopped automation adds a **↻**
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

If the launch command returns while a background service keeps running, configure
the child's optional **Background service check**. This check runs in the original
working directory: exit 0 means running, exit 1 means stopped, and other failures
or a timeout mean unknown. It is only used when no foreground process remains.

Children inherit the parent task's Objective context without taking its primary
task association. Children of a workspace main remain available under that main;
children of an Objective main appear under the active Objective's main on hover.
Task children follow the usual WIP/selected-task filter and the same parent-hover
disclosure. The fixed main itself remains a root. A launch selects
the first child unless the user has navigated to another task or workspace.

Definitions live in the workspace's `.lab/terminal-automations.json`, so every
browser sees the same saved recipes. This is separate from browser-owned tab
appearance and hierarchy. Saves reject stale revisions rather than overwriting
another settings edit. Repeating the same launch request adopts its children;
an explicit later launch starts a new group. If a later child fails to spawn,
earlier children remain running and the picker reports the failure. Restoring a
stopped terminal opens a shell without automatically replaying its command.
Original commands and launch-time guidelines are kept privately in
`.lab/terminal-automation-runs.json` for explicit recovery; refresh, reconnect and
status polling never replay them.

## Terminal tab names

Vertical tabs normally show a compact icon rail with status dots. Hover reveals
the names immediately. Leaving after a brief hover hides them again. Clicking
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

Secondary-click a child terminal and choose **Set as main** to swap its visible
row with the top parent row. The chosen child stays visible and uses its
worktree's color for its name and bullet. Its real parent and task context stay
unchanged, and **Relaunch stopped automations** remains on that real parent's
row. Choose **Restore parent as main** on either swapped row to undo the display
choice. This preference is saved in the current browser for each workspace and
vault; it does not change the fixed workspace or Objective main roles.

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
In an Objectives workspace, dropping onto a terminal's name instead stores an
independent link to the object; clicking that terminal reopens it. Tasks and
folder/worktree targets use this association without changing the launch folder
or the running process. See [OBJECTIVES.md](OBJECTIVES.md).

## Inactive terminal cleanup

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
packaged Lab capability guide while preserving each workspace's instructions.
The wrapper execs the agent; no persistent helper process or workspace agent
files are created. Plain shell tabs and attached sessions are unchanged.
See [Agent context](AGENT-CONTEXT.md) for manual launches and legacy-link cleanup.
