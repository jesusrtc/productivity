# Task assets stay put across subtasks

The user wants the Task assets section to stay at the same vertical position
when clicking tasks or subtasks. Both live and demo sidebar task lists reserve
rows for all top-level tasks plus the largest single expanded child group in
the current Objective. Keep one parent expanded at a time, and keep the reserve
when task mode closes. Use deterministic CSS grid row sizes; do not measure the
DOM on each click. Demo navigation tabs also keep a fixed height when their
icon changes. Native geometry regressions cover largest/smaller groups,
subtask navigation and closing task mode. Explicit classification or changes
to Objective assets may legitimately alter the sections above Tasks.
