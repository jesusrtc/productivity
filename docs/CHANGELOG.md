# Lab changelog

User-facing changes to Lab are recorded here alongside updates to the user
guide. This log starts on 2026-10-09; earlier repository history remains in Git.

## 2026-10-15

### Terminal messages link to work needing attention

- The terminal header lists red input requests and green finished reports across
  workspaces/vaults. Click to open the exact owning workspace, Objective and
  terminal; shared terminals produce one message.
- Red requests remain until status changes. Green messages disappear after five
  minutes from the report or when reviewed by click. Expiry does not clear the
  terminal's status, and stale clicks cannot review a newer report.
- Workspace, Home and Assistant indicators prioritize red over yellow over
  green. Submitted LLM replies immediately remove the attention message.
- Added `terminal-notifications` and `terminal-notification-open` UI commands.

### One META context document and per-terminal changelog differences

- Combined agent instructions and the complete user guide into one **Lab
  context** document in META, shared by `lab context llm` and context dragging.
  The separate user-guide entry is removed; the full changelog remains available.
- Terminal context reads include only changelog differences since the version
  acknowledged by that tmux session. A missing prior snapshot establishes a
  baseline with an explicit notice; unchanged changelogs are omitted.
- Successful output stores the changelog snapshot and then advances
  `@lab_context_version`. Launches preserve that baseline, while `llm` always
  prints full instructions. Failed output/storage cannot consume an update.

### Refresh the Lab managed instruction section

- The top-bar update/restart button now refreshes the current vault, workspace
  and selected Objective `AGENTS.md` after the new server starts. Missing files
  are created with a brief `lab context llm` startup instruction.
- The marked **Lab managed** section stays at the top and receives the latest
  template on refresh. User content outside it is preserved, duplicates are
  consolidated and already-current files are not rewritten.
- Added `lab agents refresh` and `POST /api/agents/context/refresh` for the same
  scoped action without a framework update. Symlinks and malformed sections are
  reported without replacement; ordinary creation and reads remain unchanged.

### One command loads the full agent context

- Added `lab context llm`: always print the current agent instructions, complete
  user guide and changelog, plus owning instruction paths, and mark the calling
  Lab terminal LLM-controlled. One startup line in a user's `AGENTS.md` is enough.
- Launchers now reinforce that command with a short bootstrap. They leave the
  context version unread until the agent executes the command successfully.
- `lab context update` prints the same consolidated context when changed and
  stays silent otherwise. Startup and compaction use `llm` even in a terminal
  whose version is current, so a new conversation always receives the instructions.

### Asset links automatically dock in the central work area

- Ordinary external asset clicks now try to align their real Chrome window
  over Lab's central column, with Detach, Back to Lab and Close popup controls.
  Sidebar and terminal sizing updates the reserved area; documents retain drafts.
- Permission errors, unavailable helpers and slow setup preserve the requested
  site as a regular pop-out and show a closable alert with a Settings shortcut.
  Blocked pop-ups offer a direct retry; stale attempts cannot replace a newer dock.
- Added **Settings → Global → Window docking** with an immediate per-browser
  automatic docking switch and explicit native permission/setup checks. Modified
  clicks still open tabs. This supersedes the earlier demo-only default.

### Immediate feedback for messages to LLM terminals

- Agent launches mark their terminal LLM-controlled. Added `lab terminal llm`
  and `--off` for manual control; normal refresh also detects local Codex,
  Claude and Copilot processes in the terminal's own process tree.
- Submitted LLM messages immediately show yellow. Replies to red show
  **Working - responded {response}** until the next agent report replaces the
  temporary text. Drafts, multiline paste and ordinary shell input do not trigger it.
- Hover and terminal diagnostics expose LLM control and pending submissions,
  while retaining the single centered status dot and explicit green-click review.

### Opt-in macOS window docking trial

- Added **Try docked window (Mac)** to the Objectives demo. It reserves a panel
  and uses a locally compiled Accessibility helper to align one real Chrome
  popup with Lab, with explicit Dock, Detach, Close popup and Exit trial controls.
- The helper follows geometry, coordinates minimization and attempts scoped
  focus restoration. It releases the popup after the view stops heartbeating.
  Native focus/stacking remains experimental; Accessibility permission is required.
- Ordinary links remain unchanged. The local-owner-only command endpoint is
  available through `lab api`, and the controls through `lab ui`.

### Terminal tabs keep only their status dot

- Removed Home/folder badges, extra **main** prefixes and location/automation
  dots from terminal tabs, including task, recommended and merged rows.
- Tabs retain their icons and name colors. The single agent-status dot is now
  vertically centered between icon and name, including in the compact rail.

### Inspect terminal reports and click acknowledgements

- Added `lab ui terminal-status [NAME]` to compare server reports, browser state,
  rendered dots and saved click acknowledgements without clearing an indicator.
- Finished reports retain **Reviewed by click** in hover details after their
  green dot clears. Tab and dot clicks target the displayed report ID so a
  delayed repaint cannot clear a newer finish.
- Clarified the upper-right status dot, separate lower-right location marker,
  and the existing eight-second terminal refresh cadence.

### Refresh agent context per terminal

- Added `lab context version`, which prints a numeric content ID, and
  `lab context update`, which stays silent when the calling tmux session is
  current and prints fresh context once when it changes. Each session records
  its own version; the commands do not pull code or restart anything.
- New launches record the context they supplied and identify the current Lab
  terminal/pane in the instructions. Agents must check for context updates at
  every turn, then report working and finished/attention even for short requests.
  Existing agents need to read this new rule once with `lab context update`.

## 2026-10-14

### Agents explicitly report terminal status

- Added `lab notifications working|attention|finished [message]` to set the
  calling Lab tmux terminal's indicator, with aliases `wip`, `input` and `review`.
  The launch context and `lab context` instruct agents when to report each state.
- Terminal tabs show steady yellow for working, pulsing red for attention and
  blinking green for finished, with status details on hover. Only green clears
  on a tab/green-dot click; yellow and red require a new agent report. These
  indicators send no desktop notifications, pop-ups, sounds or messages.
- Removed silence/output-based completion estimation from indicators and stopped
  capturing pane output for that purpose. Existing provider events no longer
  drive the dots. Reports follow the exact tmux session/socket and survive Lab
  backend restarts; shared workspace indicators prioritize attention.

## 2026-10-13

### Named terminal tabs show only their saved names

- Removed workspace, folder and **main** text beside named terminal tabs.
  **ASTA CLI** now appears on its own; colored location markers retain their
  folder details in hover tooltips.
- Named worktree terminals and legacy merged tabs retain their saved names
  instead of substituting a worktree label.

### Terminal headers switch one Objective at a time

- Only the active Objective's terminals unfold, including in **Show all
  terminals** mode. Other Objective headers remain clickable: selecting one
  switches the Objective and folds the previous section.
- Objective main rows now read **Main**. Generated terminal labels and folder
  badges omit repeated Objective names, while custom names, distinct worktree
  labels and full folder tooltips are preserved.

### New terminals have direct context associations

- **+ New → Current task / Objective / workflow** creates an independent
  terminal associated directly with that context. Task membership is saved
  independently of browser nesting and survives reloads.
- Task terminals share one primary for task navigation. **Make primary** on
  an independent member changes that default without turning other terminals
  into children or removing their task associations.
- Explicit subterminals, automation groups and deliberate nesting retain
  their child-terminal behavior.

### New terminals can share the current task

- **+ New → Terminal / agent → Current task** creates a new session even when
  the task already has a terminal, preserving the chosen agent and launch folder.
- The primary, including one created by an automation, keeps its role and
  running session. Task navigation continues to open the primary. The direct
  context association described above replaces the initial inherited nesting.

### vs main combines committed and uncommitted changes

- **vs main** now shows the union of committed differences from local `main`
  and staged/unstaged files. Local reversions no longer hide committed changes,
  and edits that cancel between the index and working tree remain visible.
- Every Uncommitted file is included in vs main for the same available checkout
  and filters, without duplicates. Cached snapshots use the new comparison
  immediately after refresh; worktrees and subfolders remain independently scoped.

### Make a terminal primary

- Replaced **Merge with parent** with **Make primary**. The selected child
  takes its immediate parent's position; the previous primary and siblings
  remain available beneath it, with separate consoles and asset icons.
- Task or workspace/Objective main ownership follows the new primary. Launch
  folders, saved labels, asset links and running sessions remain intact.
- Existing merged tabs can be promoted with the same action or restored with
  **Show separate terminals**. Promotion and its reverse use the same menu
  through `lab ui`.

### Terminal asset links preserve their original context

- Added **Link to asset…** / **Unlink asset** to terminal menus and **Link to
  active terminal** to asset menus. Asset drops now save a navigation link
  separately from the terminal's workspace, Objective or task ownership.
- Asset clicks activate their linked terminal; terminal clicks open the exact
  asset, subtab or URL sublink. Tabs and active headers adopt the asset's shared
  icon, including notebooks and GitHub, without changing the launch folder,
  task visibility, primary role or running session.
- Added the `terminal-asset` Objective action for CLI/API use. New file links
  outside Objectives activate in both directions; legacy file sync remains
  controlled by its existing preference until relinked.

### Launch automations directly from the New terminal menu

- **+ New → Launch automation…** creates the saved recipe's terminals for the
  active task. The first defined terminal becomes its primary automatically;
  later terminals appear beneath it, with no extra starter terminal.
- The preview labels the first terminal **Primary** and retains the chosen
  task and folder. Partial failures keep earlier sessions and their primary
  assignment; a previous primary remains running.
- API/CLI launches can omit `parent` and provide `objective_id`, `task_id` and
  optional `cwd`. Launching from an existing terminal still creates its children.

### The entire compact sidebar preserves section spacing

- Home, Vault and workspace sidebars now keep the full height of hidden Files,
  Recently updated, filters and headings. Long lists leave deliberate blank
  gaps, keeping META and its document icons aligned when hovering.
- Section shortcuts occupy their original header positions. META stays
  readable; other labels and the Links toolbar hide without changing layout.
- The inner content keeps its expanded width and prepared tree layout, so
  responsive wrapping and scroll offsets stay stable when folding.

### Task icons stay in place when the first column expands

- Hovering over the first column reveals task titles and controls without
  moving or resizing task/subtask icons or recurring markers.
- Objective headings, worktrees and pinned assets retain their vertical space
  while folded. The same chosen icon stays on the left; expanded custom-icon
  rows show their task status on the right. Subtask titles retain indentation.

### Copy asset URLs and open them in Chrome

- Added **Copy URL** and **Open in Chrome** to URL asset context menus,
  including sublinks and the Task assets dialog. Both preserve the selected
  destination's query parameters and section fragments.
- Copy reports success or failure. Explicit Chrome opening selects Google
  Chrome in local owner sessions; remote sessions use their own Chrome tab
  or explain how to open the link there. Asset metadata stays unchanged.
- Both menu actions are discoverable through `lab ui`. The shared browser
  endpoint also accepts `browser: "chrome"` through `lab api`.

## 2026-10-12

### Server Pop out and restored tabs

- Pop out opens in the clicking browser, preserving its profile and session
  instead of launching the server machine’s default browser.
- Restored server tabs load their saved mode and entry path when the Files
  sidebar cache is empty, avoiding incorrect upstream directory listings.

## 2026-10-09

### Task icons in the collapsed left sidebar

- Fixed empty task rows in the left navigation rail after status badges became
  clickable buttons. Compact task rows now retain their custom icon or default
  task emoji and remain clickable for task navigation.
- Expanded task rows retain their status badge, title and icon picker controls.

### Collapsed terminal icons and refresh visibility

- Collapsed terminal tabs retain their emojis and custom task icons; compact
  mode no longer hides icon spans.
- The refresh/renewal button appears beside the title only when terminal titles
  are visible, in both vertical and horizontal layouts.

### Stable terminal icons and hover expansion

- Task terminal icons sit on the left. Monochrome icons such as GitHub follow
  the title's custom or assigned worktree color. Ordinary task terminals use
  💻 and children use ⏺ unless a custom icon is configured.
- Expanding the vertical rail reveals titles without moving or resizing its
  icons, colored markers, renewal buttons or green review controls. Activity
  and recovery controls no longer shift collapsed icons.
- Terminal tabs no longer show yellow activity dots or task-status dots.
  Accessible activity labels and explicit green-result review remain available.

### Task icons and terminal text colors

- Clicking a task's badge or icon opens a picker with distinct asset icons,
  built-in service icons, suggested emojis and a custom emoji field. GitHub
  remains available without a matching asset.
- The picker reuses the worktree color selector for terminal text, with a
  preview, explicit Save and default resets. Choices persist through the UI
  and CLI and reach task, child, merged and recommended terminals without
  creating resources or changing worktree colors.
- WIP tasks use 🚧 and recurring tasks are marked 🔄.

### Default terminal identifiers

- The default workspace main now uses 🏠 and the default Objective main uses
  🎯 in compact and expanded lists, including dormant launch rows. Other
  terminals retain their 💻 compact fallback and custom task icons.

### Combined CLI and task navigation

- CLI task opening now follows normal task-click terminal behavior, including
  In progress selection and paused-task filtering. Named task and Objective
  navigation refresh data so preceding API changes are visible immediately.
- Added a combined browser regression covering link editing, asset assignment,
  terminal renaming, task status changes and subsequent CLI/UI navigation.

### Asset link editing and CLI access to the UI

- Secondary-click **Edit** opens an asset link modal over the current view,
  including sublinks and the Task assets dialog. Drafts, metadata, IDs and
  task/terminal associations are preserved; Command/Ctrl-click opens a tab.
- Added `lab api routes`, `describe` and `call` for the same public endpoints,
  schemas and validation used by the UI. New endpoints appear automatically.
- Added `lab ui` to inspect and operate a selected authenticated Lab view,
  including menus, fields, keyboard shortcuts, expansion and drag/drop.
  Multiple views require a chosen client; commands are never broadcast.
- Added `lab workspace open`, `lab ui rename-tab`, terminal paste and named
  document/Objective/task/terminal navigation actions. Local owner API access
  uses the existing private CLI credential with an explicit owner scope.
- `lab context cli` documents discovery, action parameters, prompts and
  asynchronous verification. Existing domain commands remain available.

### Task terminal visibility

- Task terminal tabs now appear by default only for In progress tasks. Selecting
  a paused or other non-working task, keeping a child active, or merging a child
  with its parent no longer reveals filtered task terminals. Task clicks still
  open details without starting or activating a hidden terminal. Existing
  sessions remain available through the explicit Show all controls.

### Documentation and agent context

- Added a central user guide covering context, CLI operation, documents,
  tasks, recurrence, live notebooks, local servers and migrations. Operating
  guidance previously embedded in the startup context now lives in that guide.
- Agent context supplies absolute paths to the installed user guide and
  changelog, and to existing owning vault, workspace, Objective and selected
  folder instructions. Launchers require agents to read the operating guide
  and owning instructions before working.
- Agent launches retain owning workspace/Objective identities in linked
  worktrees. Manual launches support `lab agents run --workspace <id>
  --objective <id> <agent>`; later `lab context` reads use the same ownership.
- META exposes the user guide and changelog alongside scoped instruction
  files. Both documents ship in installed packages; editable checkouts read
  the canonical `docs/` files. Read them with `lab context user-guide` and
  `lab context changelog`, or add `--path` to locate them.
- Every requested Lab change must ALWAYS update the user guide, changelog and
  relevant topic in the same change, including changes to operational guidance.

### Pending tasks and action deadlines

- Objective task navigation includes unfinished tasks and subtasks. Unchecked
  Markdown actions appear in the main dashboard and source documents, excluding
  completed and discarded branches. They no longer add rows or reserved blank
  space to the left Tasks sidebar.
- Action deadlines support `- [ ] [YYYY-MM-DD HH:mm] Action name` in local time.
  The dashboard brings overdue actions and actions due within two days forward.
  Date-only deadlines use the end of that day.
- Clicking an action opens its owning Markdown tab and highlights its exact
  line, including actions inside folded content.
- Completed recurring occurrences stay hidden until their show-again time,
  then reappear with their checklist and subtasks reset for the new occurrence.
