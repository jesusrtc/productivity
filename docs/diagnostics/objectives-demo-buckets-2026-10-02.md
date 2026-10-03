# Objectives demo asset buckets

The Home demo mirrors the current workspace layout before introducing the
experimental sidebar: Unassigned, shared Objective pins, Tasks, selected-task
assets, and collapsed Archive/Files & worktrees. The two-tab selector, hover
choices, five ordered library slots, native Markdown editor and flat terminal
groups use the production visual pattern.

`test_frontend_objectives_demo.py` passes in native Chrome. Trusted input
verifies SQL-file attachment, task selection, complete shared/task context
drags, deduplication, archive exclusion and recovery, task-terminal association,
task closing, and slot insertion that shifts later objectives and parks the
fifth. Console drops retain the simulated log and do not run the prompt. No
workspace or terminal API requests or browser exceptions occurred. JavaScript
syntax and whitespace checks also pass.

The real Home sandbox was checked with an isolated browser context. Its
`allow-scripts allow-forms` sandbox remains in place, with outbound connections
disabled. Task assignment and the unsent context prompt survived reload through
the existing browser-local adapter. A legacy three-slot snapshot without bucket
fields restored its tasks and resources under the new layout with five available
slots. Native document editing and simulated notebook execution remained usable.
No new page exceptions occurred.

Screenshots were reviewed locally at desktop width. Service and file-type icons
use the existing CSS assets; root folders stay gray. Production workspace and
Assistant metadata were not modified. Reset demo loads the new sample memberships.
