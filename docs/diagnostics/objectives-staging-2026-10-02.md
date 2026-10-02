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
