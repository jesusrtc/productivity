# Active subterminal family stays visible

The user clarified on October 8, 2026 that the active child or process terminal
must remain visible after leaving its parent or clicking the working area. Keep
its direct siblings and its entire parent/grandparent path visible too, so the
selected terminal is identifiable without hovering. Apply this only to the
currently active terminal in the current workspace; live background processes
alone do not retain their families. Do not reveal cousins or descendants just
because their branch is active. Release this exception when selection changes
to a root terminal or the child is no longer present.

Restore non-WIP family members omitted by task filtering before rendering the
terminal hierarchy. Preserve inactive Objective grouping, own-WIP visibility, ordinary
hover and keyboard disclosure, actual parent ownership and display-main swaps.
Native Chrome checks cover both rail orientations, working-area clicks,
changed polling, keyboard collapse, filtered siblings and selection changes.

This supersedes the selected-child and selected-automation folding rules in
[Subterminals without own WIP use parent hover](subterminals-without-own-wip-task-use-parent-hover.md).
