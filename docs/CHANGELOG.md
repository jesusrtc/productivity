# Lab changelog

User-facing changes to Lab are recorded here alongside updates to the user
guide. This log starts on 2026-10-09; earlier repository history remains in Git.

## 2026-10-09

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
