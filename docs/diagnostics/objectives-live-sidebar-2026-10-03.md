# Live Objective task sidebar — October 3, 2026

The user requested the task/asset workflow from the Home demo in the actual
workspace sidebar. The live sidebar now shows Unassigned, Objective shared
pins, Tasks, and the selected Task assets, followed by recoverable Archive and
fixed gray folders/worktrees. Task rows navigate; completion and editing belong
to the working-area header. One parent expands at a time. Native documents,
notebooks, services and their existing owners/renderers are retained.

The final icon request uses read-only ⬜ / ✅ status at the left, with the icon
used by tabs and linked terminals at the right. Without an override, that icon
follows completion too. Only an asset drop onto the icon area chooses a custom
icon; ordinary attachment and editing do not. Existing saved choices remain
valid. The Home demo follows the same rule, and the staging seeder no longer
initializes notebook icons automatically.

## Automated verification

The Objective/backend, native Objective/demo browser, terminal UI/completion,
and index/template regression suite passed **140 tests**. The final native
Objective fixture also passed after preserving general documents as available
assets and comparing shortcut checkout roots with their canonical paths.
Syntax checks and `git diff --check` passed.

The browser fixture checks navigation-only sidebar rows, status/icon placement,
trusted asset/icon drags, current-tab/terminal icons, shared stars that retain
task attachments, native file stars, independent parent expansion, complete
subtask reference bundles, sidebar-only reverse terminal association, retained
drafts/conflicts, and a clickable red close above native notebook controls.
Backend cases cover legacy reads without registry rewrites, atomic rejection of
invalid references, protected details, archive/recovery, and reference pruning.

## Live large-projects verification

Verified in a separate browser context using the existing local-vault staging
workspace. Normal reload served the new script and styles. The repository
navigation objective showed five top-level tasks and its selected parent's two
subtasks. The selected sample task displayed its eight required/optional assets;
its subtask displayed three own assets. The task header fit the working area,
the red close was hittable, and the sidebar had no task editing controls.

A shared star on the owned sample repository-navigation evidence document
remained present alongside its existing task attachment. This adds only a
shared Objective reference to the staging example. Resource content and
worktree metadata matched the starting snapshot. A captured subtask drag
contained **10 unique references** in Objective → parent task → subtask order.
No terminal drop or terminal input was sent during this live check.

All 11 existing terminal identities, agents, launch folders and pane processes
matched the initial snapshot. Two task icon choices and two Objective terminal
mappings changed during the open session outside these scripted checks; their
newer values were retained. Focus order was preserved. No UI exception was
captured, and the checks closed only their separate browser context.

The registry remains version 1. Absent shared/archive/shelf lists read as empty;
no JSON migration or resource storage-kind changes are required. These are
correctness checks; this report makes no new latency claim.
