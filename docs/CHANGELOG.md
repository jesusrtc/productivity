# Lab changelog

User-facing changes to Lab are recorded here alongside updates to the user
guide. This log starts on 2026-10-09; earlier repository history remains in Git.

## 2026-10-13

### New terminals can share the current task

- **+ New → Terminal / agent → Current task** creates a new session even when
  the task already has a terminal, preserving the chosen agent and launch folder.
- Additional terminals appear beneath the task's existing primary and inherit
  its task. The primary, including one created by an automation, keeps its role
  and running session. Task navigation continues to open the primary.

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
