# Lab changelog

User-facing changes to Lab are recorded here alongside updates to the user
guide. This log starts on 2026-10-09; earlier repository history remains in Git.

## 2026-10-21

### Match watched notifications to working terminals

- Replace stale green completion cards with yellow **Working** and an ellipsis
  when work resumes, including immediately after submitting an LLM message.
  Retain the last notification text and exact close target. Preserve active
  supervisor warnings, history and the agent's actual reported status.

### Fold watched notifications into hover strips

- Show watched floating notifications as compact colored status strips; reveal
  full text and × on hover or keyboard focus, preserving height and open state
  through updates. Keep full cards in history, on touch devices and for ordinary alerts.

### Use the memo-and-pencil icon for Markdown files

- Show 📝 for `.md` and `.markdown` files across file lists, linked assets,
  terminal tabs and notification cards. Preserve icon alignment and symlink marks.

### Recover disconnected automations before notifying

- Restore the automation's configured spacing (five seconds by default) for
  manual reconnects, merged renewal and automatic reconnect batches.
- Retry disconnected SSH/tmux/Mosh connections and monitored services at most
  three times, two minutes apart, with a 30-second confirmation window.
- Notify only after the third failure: one red card on the group's main with
  **Reconnect**. Preserve history, session identities, logs and agent status.
- Persist retry budgets/deadlines across restarts, coordinate manual/automatic
  requests, and protect paused tasks, live/manual work, unknown reads and replaced
  or closed sessions. Expose the independent supervisor through the shared API.

### Watch terminal notifications and schedule reminders

- Add **Watch / remind…** to terminal-tab secondary-click menus, with pinning,
  10/30-minute, 1/2/6-hour and tomorrow-at-9-AM choices plus cancellation.
- Keep the latest watched notification visible until its corner × is clicked,
  through navigation, review and working transitions. Preserve history and agent
  status; newer alerts remain available after closing.
- Persist watches per running session across clients and reloads, display due
  reminders on wake/open and expose the same controls through the shared API/CLI.
  Reject obsolete session/watch/report writes atomically.

## 2026-10-20

### Name linked terminal tabs after their files

- Linked terminal tabs and active headers show the linked file/asset's displayed
  name alongside its icon, taking precedence over the task or terminal name.
- Keep exact document-tab and sublink titles, reflect asset renames on refresh,
  and restore normal naming on unlink. Saved labels, task ownership, folders and
  running sessions are preserved, including automation and merged tabs.

### Check remote automation mains every 30 minutes

- Monitor existing SSH/tmux connections and remote processes launched by
  automation scripts. Show a recurring yellow **Check automation status** card
  on the group's main terminal only; local-only automations do not alert.
- Start a fresh window on launch/renewal, retain reminders across backend/browser
  restarts and resolve known ended connections. Unknown reads never imply success.
- Keep exact main navigation, history, actual agent status and snooze-only controls.
  A full 30-minute snooze spans recurring check-ins for the same launch.

### Snooze progress reminders without permanent dismissal

- Keep **Snooze 30 min** as the only progress-reminder control. An unresolved
  reminder returns after 30 minutes and can be snoozed again.
- Remove permanent dismissal and ignore previously saved dismissals. Keep
  timed snoozes, history, agent status and exact-alert protection.

### Restore top alerts and silence progress reminders

- Return floating alerts to the top right, below navigation. The searchable
  history center continues to open at the bottom right.
- Add **Dismiss** and **Snooze 30 min** to progress reminders. Snooze returns an
  unresolved reminder after 30 minutes; dismiss hides its current interval.
- Save choices across reloads and Lab windows in the same browser profile,
  scoped to the exact terminal and alert. Keep history, actual agent reports
  and working status intact; future reminders and input requests remain eligible.

## 2026-10-19

### Search notifications from a bottom-anchored center

- Move notification cards and the history center to the bottom right.
- Add a sticky search field for keywords across owning context, status and
  message. Case/accents are ignored; all keywords must match. Search filters
  the full history before pagination and retains typing/caret during updates.
- Show matching counts, clear search and no-match feedback. Closing restores
  unfiltered current alerts; card navigation and report-safe review are retained.

### Remind agents to report progress and flag stale WIP

- Require meaningful checkpoints at least every 20 minutes. Copilot launches
  add a process-local hook plugin that reminds after tools and checks final
  status once before allowing the turn to end, preserving existing user hooks.
- A background supervisor checks all Lab sockets every minute and retains one
  alert after 30 minutes without a report, including with the browser closed.
  New reports resolve alerts; working status and the actual message stay intact.
- Detect unclosed Copilot turns and verified local-agent exits, with unknown
  process reads preserved and two minutes of startup/wake grace. Cards retain
  native workspace/Objective labels, history, active markers and exact navigation.
- Add `lab progress status` and supervisor status/check APIs. Existing Copilot
  sessions need a relaunch/resume for hooks; other providers use instructions
  plus the independent stale monitor.

### Slide neighbouring tabs during drag previews

- Workspace and terminal tabs smoothly make room while a tab is held over its
  prospective position, including vertical and horizontal terminal layouts.
- Rapid reversals continue from the current visible position. Cancelling or
  leaving restores the strip; only dropping saves the final order. Workspace
  Home/Assistant tabs and terminal task boundaries retain their restrictions.
- Reduced motion keeps placement previews without sliding animations.


### Keep terminal tabs in task-ordered blocks

- Task and subtask order determines contiguous terminal blocks, including
  inherited children, automation members and multiple direct task terminals.
- Drag tasks above or below other tasks to move whole branches and terminal
  blocks. Alt-drag retains nesting options. Individual tab drags stay inside
  their task and never move or reassign a task.
- Saved internal tab order survives task moves and reloads. Running sessions,
  launch folders, conversations and inherited parent context are preserved.


### Refresh managed agent rules whenever a client reloads

- Administrator client reloads apply the installed template to the captured
  vault/workspace/Objective and an existing framework instruction file. This
  uses the same managed writer in every installation and preserves custom bytes.
- Restored Objective selection and cross-vault ownership are respected.
  Read-only clients do not write; malformed sections and symlinks are preserved
  with visible errors. No unrelated workspace or Objective is scanned.

### Require a status report before every final reply

- Put the working/attention/finished commands in the shared managed template,
  provider startup instructions and generated Lab managed sections,
  including short answers and approval follow-ups.
- Require a successful final status command before replying, with a normal
  permission retry for sandbox-blocked tmux access and an explicit failure
  explanation if the retry also fails. Existing status semantics are unchanged.

### Show terminal icons in notification cards

- Each active and historical notification shows its terminal's icon before
  the workspace and Objective label, using saved task, asset and automation
  choices across workspaces, including inherited icons.
- Red/green status symbols, active markers and notification navigation retain
  their existing behavior.

### Put Show all terminals in the panel header

- Added a **Show all** on/off switch beside **Terminal**, visible even when
  terminal names are folded. It saves the existing browser setting, supports
  keyboard use and stays in sync with Terminal settings.
- Removed the separate Objective **Show all / All shown** buttons and their
  saved overrides. Off consistently restores In progress and explicitly selected
  paused tasks; on reveals all statuses while retaining one expanded Objective.

### Require a WIP task for every automation launch

- The launcher requires an In progress task, lists available WIP tasks with
  their Objective names and preselects the current one. Without a WIP task,
  Launch stays disabled. API/CLI previews and launches enforce the same rule.
- The first automation row owns the chosen task and its children inherit it,
  including launches under generic workspace/Objective terminals. Pausing the
  task hides the entire group and parks its console immediately. Explicitly
  selecting the paused task reveals it until you leave.

### Show paused-task terminals only while that task is selected

- The default terminal rail includes In progress tasks, the selected paused
  task, and generic workspace/Objective terminals. Leaving a paused task hides
  its terminals immediately, including inherited children and active consoles.
- Notification navigation reveals only its exact destination temporarily,
  instead of saving Show all for the entire Objective. Legacy per-Objective
  overrides reset once; newly explicit Show all choices remain saved.
- Task clicks and `lab ui command task-open` share the same behavior.

### Keep notification history open while checking cards

- The control beside **Lid Awake** now shows only a bell and switch, with an
  accessible **Show all notifications** label. Clicking cards or receiving status
  updates keeps it on; clicking elsewhere in Lab returns to active alerts.
- Cards lead with the owning workspace and Objective. Active alerts have a
  white vertical line, which clears automatically when resolved or reviewed.
  Historical cards remain available while checking the rest of the list.
- Existing red/green behavior, exact terminal navigation, review protection,
  timestamps, pagination and fast terminal activation are retained.

### Browse the latest notification from every terminal

- Added **🔔 Notifications** beside **Lid Awake**. The center includes reviewed
  and superseded alerts, keeps only the latest notification per running terminal,
  sorts by creation time newest first, and offers 20 entries plus **Load more**.
- Clicking an alert activates its exact terminal and closes history. Clicking
  outside, close or Escape restores only active requests and unreviewed finishes,
  without acknowledging them. Current finishes still review on a successful click;
  red requests persist and historical clicks cannot clear newer reports.
- The last alert survives working status and is retained with its terminal even
  while the browser is closed, with browser retention for older CLI versions.
  History and center controls are available through `lab ui`.

## 2026-10-16

### Keep META skill trees folded until needed

- All META skill folders now start folded at every scope.
- Expanded trees stay open while visible and through ordinary refreshes, then
  fold after five minutes out of view, including hidden tabs or a different
  workspace/Objective. Returning after a delayed background timer still applies
  expiry, and cached sidebar trees cannot restore expired expansion.

### Give automations their own icons and terminal colors

- Added automation appearance controls with a terminal-outline icon, service
  icons such as GitHub, emoji and PNG upload, plus previews and a main text color.
- Main tabs default to green; children inherit the main icon and default to
  white text in the dark theme. Per-terminal icon/color overrides are optional.
- Parent names, task ownership and commands are preserved. Saved appearance
  survives browser reload and automation recovery and is available via `lab api`.

### Retire terminals belonging to inactive tasks

- Task terminals stay hidden by default outside In progress. A background check
  now stops them one hour after Completed, Won’t do or Undo/Not started, or three
  days after Paused, across registered vaults and without an open browser.
- Children inherit their parent’s task unless separately assigned. Reactivation
  cancels expiry; status changes reset the window. Exact tmux identity and task
  ownership are rechecked before stopping attached or busy expired sessions.
- Conversation identities and saved links remain available, with automatic
  restoration suppressed until explicit reopening. Legacy tasks receive a fresh
  persisted grace period. Admin status/check APIs are available through `lab api`.

### Faster notification-to-terminal activation

- Notification clicks show and focus the terminal before graphics initialization,
  avoiding a blocking first-open renderer setup. Output and input work immediately;
  graphics acceleration follows the first output paint during browser idle time.
- Exact session validation, workspace/Objective/task and linked-asset navigation,
  persistent red requests, green review and destination highlighting are retained.

### Browse skill folders at every META level

- META now shows existing skill directories for the vault, workspace, selected
  Objective and separate Files folder, covering shared, Codex, Claude and
  Copilot locations plus older Claude command skills.
- Expand each tree to browse all nested files and folders, including hidden
  and empty directories. File links retain their owning root; refresh preserves
  expansion and symlink cycles cannot recurse indefinitely.
- Skill discovery is read-only and independent of the Files dotfile toggle.
  The same scoped tree is available through `lab api` and the UI through `lab ui`.

### Confirm deletion of a whole terminal family

- Closing a parent tab now warns that all child terminals will also be deleted,
  including their count. Cancel stops nothing; confirmation closes the complete
  branch, including folded and nested children, and purges saved tabs and layout.
- Automation groups, ordinary subterminals, merged parent tabs and the
  current-terminal close action share this behavior. The same confirmation is
  available through `lab ui`.

### Space automation launches and remember expanded terminal groups

- Added **Seconds between launches** to each automation, defaulting to 5 for
  existing and new recipes. The first terminal starts immediately; 0 disables
  the delay. Settings accept up to 300 seconds, and launch previews show it.
- The server applies the saved delay for UI and CLI launches. Settings remain
  available during waits; repeat requests adopt live terminals without delays
  or replaying commands.
- Parents now show a small expand/collapse arrow when terminal names are
  visible, including automation parents. Clicking saves the group's state per
  workspace/vault in this browser and retains it across reloads. Hover still
  reveals children temporarily; active-family and WIP visibility are preserved.

## 2026-10-15

### Terminal clicks select the task and open its linked asset

- Terminal tabs and notification cards now share navigation: select the owning
  task/subtask, then open the linked notebook, file, document subtab or URL
  sublink while keeping Task assets accessible.
- Asset-only terminal links resolve their existing task assignment, including
  legacy resource links and equivalent absolute file paths. Shared assets retain
  a matching selected task without arbitrarily choosing one.
- Linked folders no longer clear task selection during terminal navigation.
  Session ownership, launch folders and the exact selected terminal are preserved.

### Notification clicks retain the owning task and its assets

- Red and green notification clicks now select the terminal's owning task or
  subtask and open its details, including inherited child and secondary terminals.
- A linked folder or asset no longer replaces task context on notification
  navigation. Task assets remain accessible, and the exact notifying terminal
  stays selected without switching to the task's primary terminal.

### Keep finished notifications until review and highlight their destination

- Green finished cards no longer expire after five minutes. They stay until
  reviewed by click or replaced by a newer terminal status, including on reload.
- Clicking a red or green card scrolls its destination terminal tab into view
  and pulses it three times. Hidden groups and the selected Objective's task
  filter open when needed; reduced-motion settings use a steady highlight.

### Floating terminal notification cards

- Terminal attention and finish messages now float in a top-right stack of red
  and green cards. They overlay the interface, keep the console size unchanged,
  and remain visible when the terminal panel is closed.
- Exact terminal navigation, persistent attention requests, five-minute finish
  expiry and red-first workspace indicators retain their existing behavior.

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
