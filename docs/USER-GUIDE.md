# Lab user guide

Lab is a local workspace for documents, tasks, Objectives, notebooks, terminals
and local applications. This guide explains how users and agents operate Lab.
Vault and workspace instructions own project conventions, content, terminology,
skills and memory policy. Explicit user requests and those instructions take
precedence over framework defaults.

## Find your context before working

A vault contains workspaces and their content. The Lab framework installation
can live outside the vault. `LAB_VAULT` pins a Lab terminal to its owning vault;
use `lab vault --help` to inspect or select vaults. A selected Files folder or
worktree may be outside the owning workspace, so its path alone does not
identify all instructions that apply.

Every agent, including agents assigned to an Objective or a task, must read:

1. This user guide and new changelog changes returned by `lab context llm` or
   `lab context update`, unless already loaded.
2. The owning vault's root instructions.
3. The owning workspace's root instructions.
4. Applicable Objective, task and working repository instructions and the
   additional files they reference.

Check existing `AGENTS.md` (or `agent.md`), `CLAUDE.md` and
`.github/copilot-instructions.md`. Read vault-wide rules first and preserve each
file's scope. Provider discovery in an Objective or linked checkout can miss
the vault and workspace roots; read those roots even if your terminal starts
elsewhere. The explicit agent-instruction refresh described below manages only
its marked section in `AGENTS.md`. Other instructions, skills and memory remain
owned by the user.

The sidebar's **META** section lists one **Lab context** document combining the
agent instructions and complete user guide, **Lab changelog**, and existing
Vault, Workspace, Objective and selected-folder
instruction files. Click a document to read it. Documentation and instruction
shortcuts expose their absolute paths in their tooltips; the context reader
lists absolute paths in its text. Switching Objectives updates the Objective
instruction shortcuts while retaining the owning vault and workspace.

META also shows existing **Vault skills**, **Workspace skills** and **Objective
skills** folders, plus skills in a separately selected folder/worktree. It checks
`skills/`, `content/skills/`, `.agents/skills/`, `.claude/skills/`, `.codex/skills/`,
`.github/skills/`, `.copilot/skills/` and Claude's older `.claude/commands/`.
Missing folders add no entries. Expand a folder to browse all nested folders and
files, including hidden and empty folders; click a file to open it at its owning
root. Skill folders start folded. Expansion survives ordinary refreshes while
you browse, then the whole tree folds after five minutes out of view, including
when you switch away or hide the browser tab. Returning before five minutes
keeps it open. This is independent of the Files dotfile toggle. Existing symlinked
skills are browsable, with cycles stopped.
These are files currently on disk; each provider decides which skills it loads.
Agents can inspect the same tree with
`lab api call GET /api/agents/context/files --query path=/absolute/scope --query include_skills=true`
or use the visible folder summaries and file links through `lab ui`.

The compact first column preserves the expanded layout's vertical spacing.
**Files** and **Recently updated** each show one section icon; their hidden
rows leave the same blank space, even for long trees. **META** and its document
icons stay at the same height. Filters, other headings and the Links toolbar
hide without closing those gaps. Hovering reveals their contents without
moving the icons or changing the sidebar's scroll position.

**vs main** combines the tracked files changed by commits relative to local
`main` with every file in **Uncommitted** (staged and unstaged edits). It keeps
both sets even when a local edit restores main's contents, and lists each file
once. On `main`, it shows the same files as Uncommitted. Each checkout/worktree
uses its own changes; new files appear after staging. Existing hidden-file and
extension filters still apply.

Click **Lab context** to inspect the combined context for the selected scope. Drag
it, or the reader's **Drag context to terminal** button, onto a terminal to paste
the full context without submitting it. The context keeps the scope captured
when opened or dragged, even if you select another folder while it loads.
Switching terminals while a drag loads cancels its paste. The context and files
show current information; they do not report what an already running agent has
loaded.

## Read the installed documentation

The top-bar **↻ Update and restart Lab** button refreshes the **Lab managed**
section at the top of `AGENTS.md` in the current vault, workspace and selected
Objective. It captures that scope when clicked and applies the newly installed
template after the server restarts. Missing files are created. Existing user
instructions stay below the marked section, unchanged; future refreshes replace
only that section, move it back to the top and remove duplicate managed sections.
Current files are not rewritten. Creating or opening a scope alone does not
write instructions.

The managed section contains just this startup instruction:

```md
Important: On startup, run `lab context llm`, read its full output and follow its instructions before working.
```

Refresh the same files without updating or restarting Lab with:

```bash
lab agents refresh --workspace <id> --objective <id>
```

Omit `--objective` for vault and workspace only; omit both for the selected
vault only. `--vault /absolute/vault/path` selects another vault. The command and
button use the same writer. They do not scan other workspaces, Objectives or
linked checkouts. Symlinks and malformed managed sections are left untouched
and reported. Keep custom rules outside the `lab:managed-context` markers.
Refreshing files does not send input to running agents; their next
`lab context update` reads changed framework context.

For a single instruction in your own `AGENTS.md`, use:

```md
At the start of every agent session, including resumed conversations, and after
context compaction, run `lab context llm` and follow its instructions before working.
```

`lab context llm` always prints the same combined Lab agent instructions and full
user guide shown in META, with absolute source paths and the applicable
vault/workspace/Objective/checkout instruction paths. Read the complete output;
increase the tool output limit or retrieve any truncated remainder. Specialized
topic guides remain available for deeper work. Reading context does not edit
instruction files. The command marks its own Lab tmux terminal **LLM-controlled**, so no
separate marker command is needed. It records the version only after successful
output and always prints again for a new conversation or context recovery, even
when that same terminal previously loaded the current version.

The changelog portion contains only the diff since that tmux session's last
acknowledged version; an unchanged changelog is omitted. The first successful
read establishes a baseline. If no earlier snapshot exists (including sessions
from older Lab releases), the command says so instead of guessing past changes.
`lab context changelog` and the separate **Lab changelog** META entry still show
the full history when needed.

These commands print documentation and do not create files in a workspace:

```bash
lab --help
lab context
lab context llm
lab context user-guide
lab context changelog
lab context user-guide --path
lab context changelog --path
lab context version
lab context update
lab agents doctor
```

In a source or editable installation, the user guide and changelog resolve to
the framework checkout's `docs/USER-GUIDE.md` and `docs/CHANGELOG.md`. In an
installed wheel or source distribution, they resolve to the installed Lab
package's `resources/docs/` directory. The context always supplies the actual
absolute paths for that installation. The package ships both documents, so a
client does not need access to the original source checkout.

Use the detailed topics for the work you are doing:

| Command | Coverage |
| --- | --- |
| `lab context markdown` | Documents, disclosures, links and copy behavior |
| `lab context notebooks` | Live execution, output and kernels |
| `lab context servers` | Local applications and lifecycle commands |
| `lab context tasks` | Assistant tasks, checklist ownership and recurrence |
| `lab context meetings` | Assistant meetings and document ownership |
| `lab context objectives` | Workspace Objectives, tasks, assets and terminals |
| `lab context migrations` | Data formats and migration procedures |

`lab agent context` and `lab agents context` are aliases. Add `--path` to a
topic to print its installed absolute file path.

After the startup bootstrap, agents must run `lab context update` at the start of every user turn, including
short requests and resumed work, before other tools. It prints nothing when the
calling tmux session has the current context. When context changes, it prints the
same consolidated context and records its version after successful output. Read and follow
that output before continuing. `lab context version` prints only a decimal
content ID; compare it for equality, not ordering. It changes automatically when
the packaged context topics, instruction-path template, user guide or changelog
change, independently of file timestamps or installation paths.

Agent launches inject a short instruction to run `lab context llm`. They preserve
the last acknowledged version so resumed conversations retain their changelog
baseline; `llm` always prints full instructions regardless. After successful
output and flush, Lab saves the changelog snapshot under
`$LAB_HOME/state/agent-context/` (default `~/.lab/state/agent-context/`) and then
updates the tmux session's `@lab_context_version` option. This live tmux option,
rather than an inherited environment variable, is authoritative. A failed read,
output or snapshot write does not advance it. Sessions track it independently, including on
older sockets after rotation. The check does not download code, restart Lab,
or edit workspace files. Outside tmux, update prints the current context each
time without saving a version. Existing agents that predate this check must be
asked once to run `lab context llm` and follow its startup/every-turn instructions;
an updated file alone cannot teach an already running agent the new rule.

## Launch agents and use terminals

Lab's New agent controls launch the selected provider with Lab context. From
an ordinary shell, use:

```bash
lab agents run codex
lab agents run claude
lab agents run copilot
lab agents run codex -- resume --last
lab agents run --vault /absolute/vault/path copilot
lab agents run --vault /absolute/vault/path --workspace <id> --objective <id> codex
```

Arguments after `--` belong to the provider. A bare provider command in a plain
shell bypasses Lab's launcher. Existing agents are not interrupted or sent
unsolicited messages when the guide changes; ask them to run `lab context llm`,
or start a new session.

Lab terminal launches also pin the owning workspace and, when associated, the
Objective. For a manual launch in an external worktree, pass `--workspace` and
`--objective` before the provider name. `LAB_CONTEXT_WORKSPACE` and
`LAB_CONTEXT_OBJECTIVE` retain those identities, so `lab context` can list the
owning instructions even outside their folders. Without explicit ownership,
Lab discovers workspace and Objective roots from the current directory.

Codex receives the startup instruction and absolute references through a process-local
developer instruction override combined with its existing trusted instructions.
Claude receives them through an appended system prompt, retaining user append
prompts and files. Supported Claude resumes refresh their system prompt unless
the user explicitly retains a snapshot. Copilot loads Lab's packaged bootstrap
instructions alongside existing custom instruction directories. Every provider
is instructed to execute `lab context llm`; `LAB_AGENT_CONTEXT` remains available
as Copilot's launch reference, with no separate environment read required.
Repository discovery, provider homes and authentication remain
provider-owned. See `lab context` for the context of the current terminal.

Opening a terminal does not itself authorize an agent to modify content. Work
within the user's request and follow the owning instructions.

One task can have several terminals. Choose **+ New**, select **Terminal** or an
agent such as **GitHub Copilot CLI**, then **Current task** to create and select
a fresh session of that type. It belongs directly to the task and appears as an
independent terminal. **Current Objective** and **Current workflow** likewise
save their chosen context without nesting beneath the active terminal. Task
membership persists across reloads and does not depend on a terminal parent.
The existing primary keeps running and task clicks still open it. **Make primary**
on another independent task terminal changes that default without nesting either
terminal. Use **New subterminal** when you explicitly want a child terminal.

Choose **+ New → Launch automation…** and pick an **In progress task** to start
a saved automation without creating a terminal first. The current WIP task is
preselected; other WIP tasks in this workspace are available with their Objective
names. A task choice is required, and no WIP tasks means Launch stays disabled.
The server checks its status again when launching. The first terminal in the automation's
definition becomes the task's primary and opens immediately; the remaining
terminals open beneath it in definition order. A previous primary keeps running.
The preview identifies **Primary** and shows every command and resolved folder.
Configure and reorder definitions in **Settings → workspace → Terminal
automations**. Each automation has **Seconds between launches**, defaulting to
**5 seconds** for both existing and new definitions. The first command starts
immediately; Lab waits the configured interval before starting each next terminal.
Choose 0 to disable the delay, or any value up to 300 seconds. The preview shows
the saved interval. Commands still run independently; this delay does not wait
for a previous command to finish. Empty or relative folders use the chosen task's
Objective folder. Secondary-clicking an existing terminal → **Launch automation…**
also requires a WIP task: the automation's first row nests beneath that terminal,
with the remaining steps beneath its first row, using the parent's launch folder.
The chosen task owns the whole automation group. Pausing it hides the group and
parks its console immediately; click the paused task to inspect it again.
See [Terminals](TERMINALS.md#terminal-automations).

Open **Icon and text color** in an automation to choose its terminal-outline,
service (such as GitHub), emoji or uploaded PNG icon. Main tabs default to green
text and matching icon color. Children inherit the main icon and default to
white text in the dark theme; each terminal has its own optional icon and color
overrides. The first terminal’s name identifies a standalone main; an existing
parent keeps its name. Settings and launch previews show the appearance before
commands run, and saved choices survive reload and automation recovery.
PNG icons can be up to 256 × 256 pixels and 64 KB. Appearance settings are also
available in the automation API through `lab api`.

The same launch is available through `lab ui` using the menu's inspected control,
or `lab api call POST /api/term/automations/launch --body-file /absolute/launch.json`.
Use `lab api describe POST /api/term/automations/launch` for the request schema.
Omit `parent` and supply the workspace, automation ID, catalog revision, a fresh
run UUID, and the active `objective_id` / `task_id`; the server assigns the first
terminal as primary. Both `objective_id` and `task_id` are required and the task
must be In progress. Supplying `parent` retains these task fields and uses the
parent's folder; omit `cwd` in that case. Set `preview: true` to check the recipe without starting it.
Save `launch_delay_seconds` on the automation through `POST /api/term/automations`
with the current catalog revision. For long groups, give `lab api call` a
sufficient `--timeout` (for example, `--timeout 180`); the response arrives after
all launches and their intervening waits.

When terminal names are visible, a small arrow beside any terminal with children
lets you **Keep child terminals expanded** or **Collapse child terminals**.
This applies to automation groups and other nested terminals. Clicking saves
the choice for that parent, workspace and vault in this browser, including
across reloads. A highlighted arrow means the group is pinned open. Hovering
still reveals children temporarily after one second and never changes the saved
choice. Existing active-family and In progress visibility rules still apply.
Agents can use `lab ui inspect` and click the parent's `[data-subtab-pin]` control.

Closing a parent terminal tab asks for confirmation that **all child terminals
will also be deleted**, with their count. Confirming closes the whole family,
including folded and nested children, and removes its saved tabs and layout.
Cancel leaves the family running. This applies to automation groups, other
parent/child tabs and merged parent tabs, whether using **Close tab** or the
current-terminal close action. Attached external sessions are detached from Lab.
Agents can use the same menu and confirmation through `lab ui`; an unanswered
confirmation cancels the close, and `--confirm yes` approves the displayed action.

To change a terminal group's primary, secondary-click a child terminal →
**Make primary**. It takes its immediate parent's position, with the previous
primary and its other children beneath it. If the parent owns the task or a
workspace/Objective main role, that role transfers to the selected terminal;
task clicks then open the new primary. Both terminals keep their own asset
links, icons, saved names, launch folders and running sessions. A terminal that
already owns a separate task cannot replace another task's primary. To switch
back, choose **Make primary** on the previous terminal. Agents can use the same
context menu through `lab ui contextmenu` and `lab ui click`.

The default workspace main terminal uses **🏠**, and the default Objective main
uses **🎯**, in both compact and expanded terminal lists, including before their
sessions start. Task terminals use **💻** and child terminals use **⏺** by
default; saved custom icons take precedence. Icons appear on the left, including
when titles are visible. GitHub and other monochrome icons follow the terminal
title's chosen color or its own assigned worktree color.

A terminal's workspace, Objective or task determines its launch folder and
visibility. An **asset link** is separate: secondary-click an asset → **Link to
active terminal**, or a terminal → **Link to asset…**. You can also drag an asset
onto a terminal tab, or an ordinary terminal onto a sidebar asset. Clicking the
asset activates its terminal; clicking the terminal opens that asset, including
the exact document subtab or URL sublink. The terminal adopts the asset's icon
(notebook, GitHub, etc.) in its tab and active header, keeping its name and origin.
This works for task primaries, automation terminals and fixed main terminals.
Terminal clicks first select the owning task/subtask and keep **Task assets**
visible while opening the linked asset within that context. Without an explicit
or inherited task link, an asset assigned to exactly one task selects that task;
an exact document subtab assignment takes priority over a whole-document one.
Shared assets keep an already selected matching task, otherwise open without
choosing an arbitrary task. Navigation does not change terminal ownership.
**Unlink asset** removes only that navigation link and restores the usual icon.
New file links outside Objectives also activate in both directions; older file
links retain their existing **Sync linked** preference until relinked.

Agents can use the same menu through `lab ui`, or apply a `terminal-asset` action
with `session_id`, `objective_id` and one `resource_id`, `file` or `folder` target
through `lab objective apply`. Add `tab_id` or `sub_link_id` for a specific child.
Use `unlink: true` with the session ID to remove the asset link. Linking does not
replace task ownership, change the launch directory or restart a session.

Hovering over the vertical terminal rail reveals titles beside the existing
icons. Icon sizes, row heights and agent-status controls
stay in place. Renewal (**↻**) appears beside the title only when terminal titles
are visible. It hides again when the rail collapses; task emojis and custom icons
remain visible. Agent-reported terminal status uses a steady yellow dot for
working, a pulsing red dot for attention, and a blinking green dot for finished.
Hover shows the status and the agent's short message. Only green clears on an
explicit tab or green-dot click. Submitting an LLM message immediately shows
yellow; the next agent report supplies the actual work status. Task-status dots
remain omitted.

Objective task terminal tabs appear by default while the task is **In
progress**, or after explicitly selecting a **Paused** task. Pausing the current
working task hides its terminals and parks its console immediately. Selecting that paused task
reveals and reuses its terminals; leaving it for another task, Tasks or the
Objective overview hides them immediately, including inherited child terminals.
Not started, Completed and Won’t do tasks stay hidden even when selected.
Selecting one of those tasks opens its details without creating or activating a terminal.
Changing it back to In progress makes its terminal available again. Hidden
sessions keep running during their retention window: **Completed**, **Won’t do**
and **Undo / Not started** get **1 hour** after the status change; **Paused** gets
**3 days**. A background check runs every minute across registered vaults and
stops expired task terminals and their inherited children, including attached
or busy sessions. Returning to In progress cancels expiry; changing to another
inactive status starts its new window. Children with their own task use that
task’s status. Workflow/Objective mains, managed servers and shared document
terminals are excluded. Conversation IDs and saved links remain available;
expired processes do not return on browser reload. Reopen them explicitly when
needed. Older tasks without a recorded status-change time receive a full window
from their first background observation, retained across server restarts.
Use **Show all** on an Objective or **Show all terminals**
in the terminal menu to inspect them explicitly; **Show WIP** restores the
In progress and selected-paused filter. Workflow and current Objective main
terminals remain available. Notification navigation temporarily reveals only its
destination, without enabling or saving Show all. Older per-Objective Show all
overrides reset once because previous notification clicks could save them;
explicit choices made afterward remain saved.

Inspect retention with `lab api call get /api/term/task-cleanup`; run a check now
with `lab api call post /api/term/task-cleanup`. Assistant task links use the same
policy: Not started and closed statuses get one hour, Blocked gets three days.
Set `LAB_TASK_TERMINAL_CLEANUP=0` in the server environment to disable the worker.

Objective headers in the terminal rail also switch Objectives. Clicking a header
selects that Objective, unfolds its terminals and folds every other Objective's
terminals. Other headers remain available, including when **Show all terminals**
is enabled; that option changes the status filter, not which Objective is open.
The Objective main row is labeled **Main**. Named terminal tabs show the saved
name alone, such as **ASTA CLI**, without extra workspace, folder or **main**
labels. All terminal rows show the icon, one vertically centered agent-status
dot when reported, and the terminal name. Home/folder badges, location dots and
extra **main** prefixes are omitted, including on automation, task and merged
tabs. Existing name/icon colors and folder details in hover tooltips remain.
An unnamed worktree terminal can use its worktree as its fallback name.

## Report terminal status explicitly

Lab agent launches mark their terminal **LLM-controlled** automatically. Agents
started manually run `lab context llm` to load instructions and mark their own
terminal (`lab terminal llm` remains available for marker-only control). Lab also
detects local Codex, Claude and Copilot processes during normal terminal refresh.
The marker appears in hover details, without adding another dot or name badge.
It persists for that tmux session. Run `lab terminal llm --off` after returning
the terminal to ordinary shell use; launching through Lab opts in again.

Submitting a message to an LLM-controlled terminal immediately turns its dot
yellow. A response while red shows **Working - responded {response}**; other
messages show **Working - submitted {message}**. The next agent report replaces
this temporary message with its actual status. Draft typing and pasted multiline
text do not start work until Enter submits it. Complex input editing uses a
generic message when Lab cannot reconstruct the text. Ordinary shells keep their
existing behavior. The immediate feedback persists and syncs between windows
in the same browser profile; it does not write a fake agent report to tmux.

Agents set the existing terminal indicator from inside their Lab tmux terminal:

```bash
lab notifications working "Implementing the changes"
lab notifications attention "Preview ready; please review the layout"
lab notifications finished "Changes complete; checks passed"
```

`wip` is an alias for `working`; `input` and `review` are aliases for `attention`.
The optional message appears on hover and is limited to 500 characters. These
commands produce no desktop notifications, pop-ups, sounds or external messages.
They discover the calling pane's session on its own tmux socket, including a
socket that is draining after rotation. Outside a Lab tmux terminal the command
fails clearly without guessing a destination.

The agent must report working on every user turn, including greetings and short
tasks such as `sleep 10`, after checking context and before doing the work;
attention before handing control back for needed input/approval/review; and finished immediately
before its final response when the requested work is complete. This instruction
is included in the launch context and `lab context`. The launch context identifies
the actual Lab terminal and pane when available. Execute the reporting commands;
describing a status in prose does not set the dot. Existing sessions need to
run `lab context update`, or receive it via **Drag context to terminal**.

Status follows the latest explicit report, with immediate yellow feedback for
submitted LLM input. Quiet output, elapsed time, terminal redraws and provider
transcript events never change it. A terminal without a report or submitted LLM
input has no status dot. Clicking a yellow or red tab opens it without clearing its
state. Clicking a green tab, including the selected tab, resets its indicator;
keyboard activation and direct green-dot review do the same. A new report
replaces the old state. Merely viewing, hovering or restoring a tab never
acknowledges green. Reduced-motion mode uses steady colored dots.

The single status dot is vertically centered beside the icon, between the icon
and name when titles are shown. Compact tabs keep the same centered status dot;
there is no second Home/folder/worktree or automation marker.
After a green report is reviewed, hover still shows **Finished · Reviewed by
click** and its message. A click can only review the finished report displayed
on that tab; it cannot consume a newer report that arrives before the repaint.

To trace a missing indicator without selecting or reviewing a terminal:

```bash
lab ui clients
lab ui --client VIEW_ID terminal-status codex-6
```

Use a logical or tmux session name, or omit the name for all terminals in the
selected view. The result compares the current server report with the browser's
report (`in_sync`), the rendered dot, and the saved click acknowledgement
(`reviewed`, `reviewed_at`, `reason`). Reports reach the visible terminal rail
through its existing eight-second refresh; short working states can finish
between refreshes. These commands diagnose actual reports without estimating
agent completion. Refresh older browser pages once to load this diagnostic.

Reports live with the tmux session and survive browser and Lab backend restarts;
a newly created session starts without a report. Acknowledgements persist in
browser storage and are shared across that browser's Lab windows and document
views. Separate browser profiles acknowledge independently. Workspace tabs
aggregate attention before working before finished; a workspace green click
reviews its finished terminals and cannot clear working or attention.
Status does not complete tasks or checklist requirements. If an agent cannot
report, Lab retains its last reported state rather than inventing a finish.

Floating notification cards appear at the top right, below the navigation bars,
for terminals across workspaces and vaults. They overlay the interface without
resizing the console and remain visible when the terminal panel is closed.
Red **Needs input** cards come first and remain until the terminal's
status changes; clicking one opens its owning workspace, Objective and exact
terminal without dismissing the request. Submitting a response turns the
terminal yellow and removes the red message immediately.

Clicking either color follows the same task-and-asset navigation as clicking the
terminal tab: select its task/subtask, then open its linked asset, or its task
details when no asset is linked. This includes asset-only links, additional task
terminals and children that inherit a parent's task. **Task assets** stay
accessible and the exact notifying terminal stays selected. Explicit task
ownership takes priority if an asset points to a different Objective.

Notification clicks connect and display the selected terminal before initializing
its graphics accelerator. The terminal accepts input and renders output during
that setup; acceleration resumes after the first output paint when the browser
is idle. Live-session validation, task/asset navigation and review behavior are
preserved. This removes graphics startup from the click's critical path, with a
local click-to-visible-terminal target below 200 ms.

Green **Finished** messages stay until reviewed by click or replaced by a newer
terminal status; they do not expire, including across page reloads.
Clicking one opens that terminal and reviews the displayed finish, clearing its
message and green indicators together. Clicking either color scrolls the
destination tab into view and pulses its background and outline three times.
Lab expands its tab group or temporarily reveals that exact terminal when needed,
without changing Show all. Leaving its task/Objective clears that temporary
reveal. Reduced-motion settings use a brief steady highlight.
Shared document terminals appear once in
the stack. Home, Assistant and workspace dots prioritize red, then yellow,
then green. No desktop notifications or separate popup windows are sent.

Use the **bell and switch** next to **Lid Awake** to show all notifications.
The control has no visible text; its tooltip and accessible name are **Show all
notifications**. It shows each running terminal's latest red or green notification,
including reviewed finishes and alerts replaced by working status, newest
creation first across all workspaces and vaults. The first 20 appear initially;
**Load more** reveals 20 more. Shared terminal views count once. Past alerts
are labeled **History** and show their creation time. The latest alert is saved
with its terminal session, including when the browser is closed. Browser storage
also retains observed alerts from older CLI versions. Alerts already replaced
before this feature was installed cannot be recovered.

Each card puts its owning workspace and Objective first, before the terminal,
vault and status. Active alerts have a white vertical line; reviewed or superseded
history does not. Answering a request, reviewing a finish or receiving a newer
status automatically updates that marker. Existing red/green messages keep their
normal status behavior.

Clicking a notification activates its exact terminal and keeps **Show all** on,
so you can check several cards in sequence. Status changes and refreshes also
keep the list open. Clicking another area of Lab, turning the bell switch off,
the close button, or Escape closes history. The normal stack then
shows only current input requests and unreviewed finishes. Dismissing history
does not review anything; clicking a current finish reviews that displayed
report, while red requests remain active until answered or updated. Opening an
older finish cannot clear a newer report or change a working terminal's status.

Agents can inspect the same messages with
`lab ui --client VIEW_ID command terminal-notifications`, then open one using
`lab ui --client VIEW_ID command terminal-notification-open --json '{"name":"TMUX_SESSION","report_id":"REPORT_ID"}'`.
Use the exact session and report returned by the first command.
Add `--json '{"history":true}'` to `terminal-notifications` to list history.
`lab ui --client VIEW_ID command terminal-notification-center` opens the same
center with the bell switch on; `--json '{"open":false}'` turns it off. **Load more** and the close button
are also available through `lab ui inspect` and `lab ui click`.

## Change metadata through Lab

Discover the relevant CLI with `lab --help` and each command's `--help`. Use
`lab` to change workspace and task metadata. Never hand-edit `workspace.json`,
`tasks.json` or `.index.json`. Markdown documents are content and may be edited
directly when the user authorizes that work.

For workspace Objectives, read `lab context objectives` and inspect the current
state with `lab objective ls --workspace <id>`. Mutations use
`lab objective apply`; consult its help for supported actions.

When inferring where an existing asset belongs, write only a
`suggest-assignment` action. Include the existing asset identifier, destination
task/Objective and an evidence-based reason. Suggestions remain pending for
the user's Accept/Reject controls. Do not accept your own suggestions, repeat
an identical rejected suggestion, or use assignment, star, bucket, trash or
removal actions to implement inferred organization without an explicit user
request for the actual change.

## Operate the same UI through the CLI

Every public Lab API is discoverable with `lab api routes`, including new
endpoints. `lab api describe METHOD /api/path` shows its parameters and JSON
models; `lab api call METHOD /api/path --body-file request.json` invokes the
same handler and validation as the UI. Repeat `--query KEY=VALUE` for query
parameters, including the owning vault/workspace. Existing domain commands
remain available; use them or the shared API instead of editing managed JSON.

Browser-only actions use `lab ui`. Open or reload Lab, run `lab ui clients`,
then select the intended view with `--client ID` (or `LAB_UI_CLIENT`). A single
connected view can be used without that option; multiple views require an
explicit selection. `lab ui --client ID inspect` lists visible controls and
unique selectors. Use `click`, `contextmenu`, `fill`, `key`, `hover`, `scroll`,
`drag` and `wait` to operate those controls and their actual menus and dialogs.

Named `task-open` and `objective-select` actions refresh Objective data before
navigating, so they see preceding API changes immediately. Opening a task by
CLI follows the same terminal policy as clicking it: In progress and selected
paused tasks activate their linked terminal. Leaving the paused task hides its
terminals under the default filter.

```bash
lab workspace open demo --vault my-vault --client VIEW_ID
lab ui --client VIEW_ID rename-tab TERMINAL_NAME 'Review'
lab ui --client VIEW_ID inspect
lab ui --client VIEW_ID contextmenu 'ASSET_SELECTOR'
lab ui --client VIEW_ID click 'EDIT_SELECTOR'
lab ui --client VIEW_ID fill 'URL_SELECTOR' 'https://example.com/new'
lab ui --client VIEW_ID click 'SAVE_SELECTOR'
lab ui --client VIEW_ID wait '[data-link-details-status]' --text Saved
lab ui --client VIEW_ID key Escape
```

Secondary-click an asset link and choose **Edit** to edit it in a modal over
the current task/document. Sublinks and the Task assets dialog have the same
action. Save preserves the asset's identity and task/terminal associations;
close/Escape retains drafts. Normal asset link clicks try to dock a real
Chrome window over the central work area; if unavailable, they open a regular
pop-out with a dismissible setup message. Command/Ctrl-click opens browser tabs.

URL assets also offer **Copy URL** and **Open in Chrome** in that menu,
including sublinks and the Task assets dialog. Copy keeps the full saved URL,
including query parameters and section fragments, and confirms when copied.
Open in Chrome explicitly launches Google Chrome for a local owner session.
In remote sessions, it opens a tab if you are already using Chrome; otherwise
it explains how to open the link there. These actions leave asset details and
assignments unchanged and are available through `lab ui` menu controls.

`lab ui paste TEXT --terminal NAME` pastes through the selected terminal;
`--file PATH` accepts longer text, and `--submit` explicitly sends Enter.
Native prompt answers use `click --prompt VALUE` or `--confirm yes|no` for that
invocation only. Custom deletion dialogs retain their confirmation steps.
Use API reads and `wait` to verify asynchronous changes; a timed-out command
may have run, so inspect before repeating it. API/CLI credentials stay local
and owner-readable. See `lab context cli` for the full command/action map and
browser-native permission limitations.

## Dock asset windows in the central work area (Mac experiment)

Click an external asset link in an Objective, task or folder, including a
sublink or its editor's **Open** button. Lab automatically tries to align a
real Chrome popup over the central working area. The sidebar and terminal
remain accessible, and the underlying document and unsaved drafts stay mounted.
The website is a top-level page in your Chrome profile, with no iframe, opener
or referrer. Command/Ctrl-click still opens a normal browser tab.

Open **Settings → Global → Window docking** (or use the setup alert's
**Window docking settings** button). **Automatically dock asset links** is on
by default; switching it off immediately restores ordinary pop-outs in this
browser. Docking requires local administrator access to Lab on macOS, Google
Chrome, Xcode Command Line Tools and permission for **Lab Window Dock** under
macOS **System Settings → Privacy & Security → Accessibility**. Choose
**Enable window control**, enable that helper in macOS, then **Check
permission**. Allow pop-ups for Lab in Chrome. These setup actions are explicit;
clicking an asset does not request OS permission automatically.

Missing permission, unavailable helpers, errors, small central areas and
setup delays leave the site open as a regular pop-out. A closable alert explains
the problem and links to settings. A blocked pop-up instead offers **Open site**
and asks you to allow pop-ups. The initial docking attempt falls back after
eight seconds; late helper responses cannot replace the current dock. If the
connection later fails, Lab releases alignment and shows the same kind of alert.

**Detach** or **Back to Lab** restores the central area and keeps the website
open independently. **Close popup** closes only the registered window. Opening
another asset or navigating away releases the previous dock without closing its
site. The reserved area follows sidebar and terminal sizing. Settings dialogs
and inactive Lab tabs temporarily hide the docked popup; the helper restores it
when appropriate. A lost browser heartbeat releases alignment within twelve
seconds. Chrome's frame remains visible, and native stacking, focus, Spaces and
movement smoothness remain experimental. Remote clients use ordinary pop-outs.

The manual **Home → Objectives demo → Try docked window (Mac)** trial remains
available. Agents can use `lab ui --client VIEW_ID` to click asset links, open
Settings, toggle `[data-dock-auto]`, or use `[data-dock-permission]`,
`[data-dock-check]`, `[data-dock-detach]`, `[data-dock-close]` and
`[data-dock-alert-dismiss]`. The native endpoint is discoverable with
`lab api describe POST /api/ui/window-dock`; it requires the exact Lab origin
and a local administrator. See [Window docking](WINDOW-DOCK.md) for validation
and separate rollback instructions for automatic docking and the original trial.

## Tasks, subtasks and action items

Task Markdown checklists represent required work. Checked and pending counts
affect progress, and pending items prevent task completion. Use concrete
actions grounded in the user's actual requirements. Preserve existing wording;
change requirements only when authorized. Do not invent scope, add filler,
delete pending items to claim completion or check an item without verifying
its work.

The Objective Tasks sidebar shows unfinished task and subtask navigation.
When the left sidebar is collapsed, each task still shows its selected custom
icon or its task status emoji. Click that compact icon to open the task; hover
expansion reveals the title and controls beside the same icon. Task and subtask
icons keep their position and size in both states, including recurring markers.
The headings and pinned assets above Tasks retain their height, so hovering
does not shift the task list. Subtask indentation applies to titles; their
icons stay in the fixed icon column. Custom icons remain on the left, with the
task status shown on the right when expanded.
WIP tasks use **🚧** and recurring tasks carry **🔄**. Click the task's status
badge or its icon area to open **Task icon and terminal color**. The picker
starts with distinct asset icons and built-in service icons, including GitHub
even without a GitHub asset, followed by suggested emojis and a custom emoji
field. **Terminal text color…** opens the same palette used for worktrees.
Preview both choices, then **Save**; **Default icon** and **Default color**
restore the existing defaults. Choices persist and apply to linked task
terminals, including inherited children and merged tabs. Secondary-click still
opens the task status menu.

Unchecked Markdown actions appear in the main task dashboard and their source
document, without adding rows or blank space to the left sidebar. Completed and
discarded branches are excluded. The dashboard highlights overdue actions and
actions due within the next two days. Write an action's deadline at the beginning of its text:

```markdown
- [ ] [2026-10-12 09:30] Review the alert proposal
- [ ] [2026-10-12] Send the revised document
- [ ] Prepare the agenda
- [x] Review the previous draft
```

Use `YYYY-MM-DD HH:mm` in local time, with a 24-hour clock. Date-only deadlines
use the end of that day. Undated actions remain pending. Click an action to
open its owning Markdown tab, reveal folded content and highlight the exact
action; entering Edit selects its source line.

Recurring tasks keep their ID across occurrences. A completed occurrence
stays hidden until its **show again** time. At that time Lab reopens it and
resets its existing checklist and subtasks, so the new occurrence appears
unchecked. The show-again lead can be configured; the default is one day before
the next deadline. Overdue unfinished occurrences stay obligations rather than
being skipped.

Icon and color settings also use `lab objective apply` with a `task-update`
action. Use `icon: {"emoji":"💡"}`, `icon: {"service":"github"}` or
`icon: {"asset":{"resource_id":"ID"}}`, and `terminal_color: "#58a6ff"`.
Set either field to `null` to restore its default. Icon selection alone does
not attach an asset or change task status or worktree colors.

For Assistant tasks and meetings, read `lab context tasks` and
`lab context meetings` before editing their source documents. Only an explicitly
linked content tab owns an Assistant task's checklist; inheriting a navigation
tab does not create checklist requirements for a subtask. Follow client rules
for ownership, research and writing.

When `LAB_DOCUMENT_CONTEXT` is set, read that JSON file for the current absolute
Markdown path and tab ID before working on an Assistant document. This context
does not authorize edits. Preserve sibling documents and tabs. If present,
`LAB_ASSISTANT_HOME` selects the owning Assistant database.

## Documents and foldable supporting material

Lab reads Markdown documents and supports HTML disclosures:

```markdown
<details><summary>Supporting calculation</summary>

An explanation, code, a table, an image or a note goes here.

</details>
```

Keep blank lines around the inner Markdown. Closed disclosures, including
their labels, are excluded from Google Docs copy. Open disclosures are copied
as ordinary content. Use this for supporting material the user wants folded.
See `lab context markdown` for examples and other document behavior.

## Run notebooks live

When notebook work should appear live in Lab, use Lab's executor so the cell
appears as execution starts and its timer and outputs stream to open views:

```bash
lab notebook exec workspaces/<id>/notebooks/<name>.ipynb --code 'print(1+1)'
lab notebook exec workspaces/<id>/notebooks/<name>.ipynb --cell-id <id> --file /tmp/cell.py
```

The kernel is pinned to the notebook path, so consecutive cells share state.
Direct kernel execution bypasses the live UI. Read `lab context notebooks`
for constraints, interruption and execution details.

## Expose local applications

Configure workspace server tabs and proxies in `servers.json`, with `make`
commands for their lifecycle. Do not add proxy declarations to `workspace.json`.
Read `lab context servers` for the supported format.

In an embedded server view, **Pop out** opens the configured app in the same
browser you are using for Lab. Restored tabs load their saved server settings
even before the Files sidebar is ready, preserving the configured entry path.

In a framework source checkout, resolve the running Lab URL with
`scripts/lab-url.sh`. Its configured port may differ between installations and
from the default. The active vault records the running port at
`.lab/state/server.port`; do not hardcode a localhost port in tooling or links.

## Migrate existing data

Read `lab migrations` or `lab context migrations` before migrating. Individual
guides include `assistant-document-tasks`, `assistant-documents`,
`assistant-subtabs`, `assistant-records-v2`, `workspace-agent-context` and
`vault-workspace-names`, for example:

```bash
lab migrations assistant-records-v2
```

These commands print documentation only. Inspect the current format and local
instructions, preserve IDs, content and references, and migrate only within
the user's authorized scope. `lab agents sync` is a read-only compatibility
check. `lab agents detach --dry-run` previews removal of recognized legacy
integration links without altering their targets; see the migration guide
before applying it.

## Keep Lab documentation current

ALWAYS update this user guide with every Lab change the user requests,
including changes to operational guidance. Update `docs/CHANGELOG.md` and any
relevant topic in the same change; documentation is required work. Explain the
resulting behavior and how to use it, including migration or compatibility implications
when applicable. Record dated changes without claiming an exhaustive history
for versions that predate the changelog.

The source checkout's `docs/USER-GUIDE.md` and `docs/CHANGELOG.md` are canonical.
Package builds include those exact documents; do not maintain separate manual
copies for installed clients. Keep domain-specific instructions in their
owning vault or workspace.
