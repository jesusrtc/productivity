# Child terminal main is a display preference

The user wants to secondary-click a child process terminal and set it as main:
swap its visible row with its immediate parent's row and use its worktree color.
Keep the actual child/parent relationship, session identity, task inheritance
and automation recovery ownership unchanged. Batch relaunch stays on the real
parent. The nominated child is an explicit exception to parent-hover-only
disclosure and remains visible. Restore parent as main undoes the display
choice. Persist it in browser-local terminal group state, scoped by workspace
and vault, without changing fixed workspace/Objective primary roles.

The immediate-parent correction is documented in
`child-main-swaps-immediate-parent.md`; never walk up to the tree root for this action.
