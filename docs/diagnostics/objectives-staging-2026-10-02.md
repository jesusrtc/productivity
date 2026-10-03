# Objectives staging verification — 2026-10-02

The real workspace feature was tested in the user-designated `large-projects`
staging workspace. Four simulated objectives use six registered worktrees:
Linux/LLVM, Kubernetes/CPython, and Rust/Git, with a fourth saved investigation.
Three dedicated `objective-staging-*` shell sessions exercise terminal grouping
and resource navigation. The seven existing user terminals received no input
or metadata changes.

## Requirement audit

| Requirement | Verified behavior |
| --- | --- |
| Three objective selectors atop the left column | Three compact rows; selecting one opens its tasks in the center. Bringing in the fourth replaces an explicit slot and retains the parked data. |
| Shared resources before worktrees, recent files and Files | Objective resources and the single Tasks item precede the associated worktrees and native file sections. Scoped resources appear beneath worktrees. |
| Worktree association replaces pinning | Every associated worktree is rendered. The existing chooser/create workflow now associates its selected checkout with the objective. |
| Distinct reserved colors | Twelve reserved worktree colors across three objectives are globally unique; duplicate checkout membership is rejected. |
| One Tasks item with status | Completion, on-track, due-within-two-days and overdue statuses render in green, yellow, orange and red. Completing all four staging tasks displayed green `4/4`. |
| Compact tasks and mandatory document details | Task/subtask rows have checkboxes, dates and detail buttons. Creating a task creates an embedded details subtab; child tabs nest beneath parent details. |
| Documents and notebooks can be created and renamed | Created and saved a task-details document through the UI. Created `UI quick notebook.ipynb` with two native cells and renamed the analysis notebook through its header. |
| Immediate document subtab tree | Clicking a document revealed all nested rows; clicking a child opened its standalone detail view. |
| Hover and pinned-only retention | Hover revealed subtabs after 1.5 seconds. Selecting Tasks retained only pinned rows; the same pins survived a page reload. |
| Resource drag and drop | Actual UI dragging scoped the PR link to another worktree, hid it on the first, showed it on the second, and restored it to shared resources. |
| Terminals grouped by objective and worktree | Three focused groups displayed native session pills under their fixed checkout folders. |
| Terminal resource association | Dropping a document on the dedicated phone shell associated it; clicking that terminal opened the document and preserved its launch folder. Backend tests cover notebook and shared Assistant-terminal mappings. |
| Assistant keeps its ownership and behavior | An existing Assistant reference and its subtab opened inline with the workspace sidebar visible. Tests confirmed unchanged original bytes and unchanged owner/session metadata. |
| Native notebook display and live execution | The native cells and outputs rendered. `lab notebook exec` produced simulated volume total `85`. A later rename retained the same kernel ID and the variable value `85`. |
| Existing text sizes | Computed objective selector/worktree size `11px`, resource/subtab/task size `12px`, Files and owned non-modal Markdown size `13px`. No horizontal overflow at the native narrow sidebar width. |
| Conflicting browser writes | A concurrently changed registry rejected a stale creation with a refresh/retry message; retry created the notebook without overwriting the other state. |

## Native click measurements

The final run used a fresh native Chrome profile at 1550 × 1050, the real server,
normal polling, existing large repositories and the three owned shells. Mouse
input was dispatched externally with a wall-clock source timestamp. Every
sample retained input queue time, checked the final visible content and included
an animation-frame/task paint opportunity. Clock samples were validated against
the dispatch timestamp. First-use samples were retained.

All **90 clicks passed below 200 ms**. Maximum: **188.5 ms**; maximum input
queue: **9.1 ms**. No browser exceptions occurred. The selected Objectives and
sidebar API requests had a maximum resource duration of **97.8 ms**.

| Interaction | Samples | Maximum ms |
| --- | ---: | ---: |
| Objective selector → tasks | 9 | 41.1 |
| Document → body and expanded tree | 9 | 36.1 |
| Nested subtab → body | 9 | 39.6 |
| Pin | 9 | 35.7 |
| Tasks → pinned-only tree | 9 | 36.3 |
| Task checkbox → checked state | 9 | 39.6 |
| Worktree → final root Files | 9 | 54.0 |
| Notebook → final cells | 9 | 57.2 |
| Original Assistant reference | 3 | 178.6 |
| Original Assistant subtab | 3 | 188.5 |
| Linked terminal → document | 3 | 36.9 |
| Unpin | 9 | 36.6 |

The task check measurement covers immediate visible confirmation; the probe
separately waits for the stored result before the next operation. These results
cover the listed ready-workspace interactions, not initial workspace loading,
arbitrary document sizes, remote page loads, kernel computation, or physical
display latency. The 1.5-second hover delay is intentional and is not a click.

[All 90 sanitized samples](objectives-staging-2026-10-02.json) retain their
durations and clock-validity results, excluding authentication, source document
bodies and terminal contents.

## Automated checks

| Check | Result |
| --- | --- |
| Objectives, workspace documents, scope links and project sidebar backend suites | 58 passed, including 10 new Objective ownership/conflict/mapping tests |
| Frontend scope links, workspace documents and terminal task navigation | 9 passed |
| Frontend sidebar scopes, cache, file configuration and workspace documents | 47 passed |
| Local notebook runtime, notebook identity and kernel failure suites | 21 passed |
| JavaScript syntax, Python compilation, CLI help and whitespace checks | Passed |

Three older workspace-document fixtures conflicted with the existing fixed
launch-folder policy. Their failures were reproduced from the unchanged base
commit. The fixtures now launch each terminal in its intended folder and assert
that clearing a saved folder is rejected; production terminal behavior was not
changed for these fixes. Frontend and notebook process tests used the needed
local Chrome/socket permissions.

## Reproduction

Select the authorized staging vault before running either script. The seed uses
Lab mutations and registered worktree paths; re-running reuses the named fixture.
The click probe changes only simulated task completion and browser-local pins.
It sends no input to terminal processes. It expects the three focused staging
objectives and their dedicated shells to remain available.

```bash
LAB_VAULT="<staging-vault>" core/.venv/bin/python scripts/perf/seed_objectives_staging.py
LAB_VAULT="<staging-vault>" core/.venv/bin/python scripts/perf/objectives_staging_latency.py \
  --workspace large-projects --output /tmp/objectives-staging-latency.json
```

The wrapper resolves the server URL through `scripts/lab-url.sh`; its temporary
authentication stays in the subprocess environment. The fixture and three
dedicated sessions are left available for interactive review. The Home demo
continues to use separate browser-only data.

## Follow-up: flat terminals, fixed folders and live editing

Terminal rows now retain their native pills, grouped by objective and canonical
checkout, with a small project header and one thin colored left rail. Worktree
boundaries use spacing; project boxes and visible worktree headings are removed.
Legacy shortcut paths resolve to their real checkout without rewriting the
saved registry. Tasks moved directly below the objective selectors. Fixed gray
Root and Objective rows open the workspace and selected objective directories;
the Objective path changes when another objective is selected. An existing
explicit Root association is deduplicated while keeping its scoped resources.

Owned Markdown opens directly in the existing live editor, including from the
native Files tree. Native formatting and slash commands work; `/fold` created
a foldable block in an owned staging document. Save during ongoing typing,
outgoing navigation saves, child-only edits and external conflict recovery were
checked against the real server. Linked original Assistant documents retained
their native editor and source ownership while their inner tab rail/drawer were
hidden for this Objective presentation. No original Assistant content was edited.

The Objective backend suite passed **11 tests**. The new real-API/native-editor
regression passed: it holds a parent save response, types newer parent and
child content, checks both saved bodies and the untouched sibling, waits for
ten-second idle autosave, and recovers from a rejected concurrent edit. Existing
live-editor, formatted-editor, scope-link and terminal-navigation suites passed
**10 tests**. JavaScript syntax, Python compilation and whitespace checks passed.

The expanded probe adds nine workspace Root and nine Objective-folder clicks,
and document readiness requires the mounted editable native editor. Two fresh
Chrome runs each retained **108 samples**. The first had one Assistant subtab
sample at **242.3 ms**; its other 107 clicks were below 200 ms. Its layout
assertion mistakenly counted native `SPAN.sess` pills as worktree headings;
the selector was corrected without changing application code. The repeat had
all 108 clicks below 200 ms, maximum **130.2 ms**, and no browser exceptions.
These results retain the first-run miss rather than implying a universal
200 ms guarantee. Both runs used normal polling and the same bounded native
sidebar projection cache. [Sanitized samples from both runs](objectives-refinement-2026-10-02.json)
include clock validity and the verified gray roots, Tasks position and left-only
terminal borders.

## Follow-up: All and five workspace focus tabs

Workspace navigation now shows All and five vault-style objective slots.
The sidebar's selector list was removed and Tasks is its first item. All lists
focused and parked objectives, with name/outcome search and focus/task-status
filters. Actual UI drags filled an empty fourth slot, replaced the fifth slot
with a sixth simulated objective, brought the previous fifth objective back,
and swapped two filled slots in both directions. All original resource, task,
worktree and terminal-link projections remained identical during these focus
changes; the fifth and sixth fixtures are independent simulated content. Five
focused project colors were distinct. All remained visible across normal polls
after fixing a startup reconciliation that could restore the old dashboard.

Workspace Overview, Code Search, Jupyter, Logs and Cleanup tabs are removed.
Configured server tabs retain their existing renderer. Global Logs/Cleanup are
adjacent header controls. Cleanup was opened read-only: its workspace tabs
included empty workspaces, opened on the current one and supported keyboard
navigation. No cleanup kill button was pressed and no user terminal received
input.

Checks passed: **12 Objective backend tests**, the real-API/native-editor test
including native search and exact fifth-slot assignment, **22 cleanup tests**,
and **71 frontend notebook/navigation/logging/cleanup/sidebar/server tests**.
An older notebook CSS assertion searched the entire stylesheet and incorrectly
matched another component's `margin-bottom:22px`; it now checks only the
notebook toolbar. Chrome process tests ran with their required permissions.

The expanded native probe retained **117 clicks**, including nine All-library
opens. **116 were below 200 ms**; the first Assistant subtab took **285.0 ms**.
No browser exceptions occurred. All/top-slot layout, Tasks-first sidebar,
gray roots and flat terminal rails passed. This is measured evidence for the
listed interactions, not a universal latency guarantee.
[All sanitized five-tab samples](objectives-five-tabs-2026-10-02.json) retain the
first-use miss and every validated input clock.

## Follow-up: sidebar references and arbitrary terminal targets

Actual native UI drops into the dedicated phone staging shell passed for ten
object types: owned document/subtab, Assistant document/subtab, notebook, URL,
Tasks, workspace Root, Objective directory and worktree. Each pasted its exact
source reference with shell quoting and no Enter. References were cleared from
that owned shell without submitting commands.

Native drops onto the owned terminal name persisted associations for those
same object types plus ordinary Files and folder rows. Clicking the terminal
reopened the documents/subtabs, notebook, Tasks and folder/worktree browser.
The external site's association was checked without opening the public site;
URL dispatch is covered in the isolated native Objective fixture. Dragging the
terminal onto Tasks also worked and cleared the terminal reorder state.

Objective resources, tasks, worktrees and focus slots remained unchanged. The
owned shell's original Objective mapping was restored and every terminal's
saved identity, launch folder, command, label, agent session and original links
matched its baseline. There were no page exceptions. The existing staging tab
stopped delivering native input during the first probe, so the verification
used a fresh test tab; no application workaround was introduced.
[Sanitized native drag results](objectives-object-drops-2026-10-02.json) contain
the per-type results and preservation checks.

Focused regressions passed for source identity, URL/subtab quoting, invalid
references, original Assistant ownership, Tasks/folder association, folder
boundary rejection, and native file/sidebar behavior. The real-API Objective
fixture also verifies that associations send no terminal input and preserve
session metadata while retaining its existing editor/save/conflict checks.

## Follow-up: one current tab, ordered slots and shared icons

The current UI has Objectives plus one current-objective tab. Native hover
shows five numbered choices below the scrolling tab strip. Library slots sit
above the filters; a native result drag inserts at slot 1, shifts the following
four objectives and parks the previous fifth. The real-API fixture verifies
that parking/refocusing retains document siblings and the terminal identity.
Keyboard menu entry, Escape, selection and slot color changes also pass.

All **14 Objective backend/browser tests pass**. Fixed slot palettes apply to
objective headers and associated worktrees, including existing registries on
read. The native staging view shows colored associations and rails only in
the current objective; other groups keep their colored header and gray rows.
No terminal input was sent during these checks.

Generic `.ipynb` and `.sql` references use the same file extension icons as
Files; the browser fixture includes both alongside an owned notebook. Native
checks confirm service mappings (including an Observe domain mapped to Grafana),
custom PNG icons, and the unknown-service arrow. These mapping checks ran only
in a disposable page's memory and did not save client settings. Shared and
worktree-scoped resources use the same resource-row renderer, without metadata
migration or changes to opening/ownership. No staging page exceptions occurred.

## Follow-up: editable link details and nested destinations

All **17 Objective backend/browser tests pass**. The native fixture verifies
ordinary clicks open editable link details without an iframe, saved title/URL/
TL;DR and properties persist, and unchanged numeric/array metadata retains its
JSON type. Cmd-click leaves the current working view in place while dispatching
the exact URL. Open uses the edited valid URL; invalid URLs disable it. Conflicts
retain the draft and Revert loads the saved details.

Adding a sublink persists a stable child ID. The sidebar child stays hidden
before the one-second parent hover delay, then appears beneath the parent.
Child details save independently; console drags use its URL and terminal
associations reopen that exact child. Backend checks cover nested additions,
duplicate/depth rejection, atomic invalid writes, and subtree removal falling
back to the parent resource association. Legacy links need no migration.

A fresh native `large-projects` staging page opened the existing Sample release
checklist link: its editable Google Docs details appeared with no iframe and
no page exceptions. This staging check saved no resource changes, opened no
external site and sent no terminal input.

## Follow-up: task hyperlinks, assets and focus modes

The Objective suite now covers **22 backend/browser tests**, alongside **103
terminal UI/completion checks**. Task titles are real hyperlinks, ordinary
clicks open their required document subtabs, and Focus shows only required
details and attached assets. Off restores the usual sidebar; Semi restores it
with highlights in its original order. The native fixture verifies an actual
notebook-to-task drag using Chrome input and the real API, followed by document,
file, folder, worktree and URL attachment paths.

Tasks choose an icon from an attached asset. The current working tab and a
linked terminal inherit it while keeping terminal activity/completion signals.
Terminal-to-task and task-to-terminal drops retain saved sessions and send no
input. A console task drop carries all references in one shell-quoted, unsent
paste: details with its subtab ID, then every attached document/notebook/file,
folder/worktree and URL. The regression checks the full bundle rather than
just its first item.

Backend checks cover deduplication, subtask isolation, exact document and link
children, retained shared/worktree scopes, original Assistant content/ownership,
folder boundaries, stale writes, detachment and icon fallback. Required details
cannot be detached. Existing tasks require no registry migration.

A fresh `large-projects` page opened an existing release task into its native
document editor. Focus hid native Files; Semi restored the Files controls and
folders plus both fixed roots, highlighting the task's details. Off removed the
highlights. Controls remain usable at the existing narrow sidebar width, and
the page raised no exceptions. This staging check saved no resource/task changes
and sent no input to existing terminals.
