# Objectives demo task mode and asset gestures

Scope: browser-only Home Objectives demo, following the earlier asset-bucket
redesign. No production Objective or Assistant data migrations.

## Behavior

- Left task rows navigate and show status; editing/completion are in the
  middle task view. Only the selected parent task's children unfold.
- Task mode retains the task's name, icon, completion and red corner close
  while opening a notebook or another asset.
- Subtask console bundles include shared Objective references, the parent's
  details and assets, then the subtask's details and assets; exact subtabs are
  preserved, duplicates removed, and Archive omitted. Input remains unsent.
- Terminal drags associate only with left-column targets. Unassigned opens
  the middle task list, which accepts asset attachment drops.
- Stars share or unshare any asset without removing task membership. An
  asset drop onto a task's icon also attaches an unassigned source as needed.

## Verification

`core/tests/test_frontend_objectives_demo.py` passes using isolated Chrome and
trusted native CDP mouse/drag input. It covers header completion (parent and
subtask), exclusive task expansion, ancestor context ordering, exact subtab
stars, icon propagation and attachment, shared/task deduplication, Archive
recovery, terminal-to-subtask/file/worktree associations, rejection of middle
terminal drops, asset-to-middle-task attachment, task closing, and five-slot
insertion. The demo makes no workspace/terminal API calls, and no renderer
exceptions were recorded.

The authenticated Home demo was also checked in a fresh browser context.
The native Markdown editor loads, and active subtask, expanded parent,
completion and shared-star state survive a page reload without renderer
exceptions. JavaScript syntax and whitespace checks pass.
