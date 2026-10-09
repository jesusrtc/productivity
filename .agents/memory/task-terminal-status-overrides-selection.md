# Task terminal status overrides selection

On October 9, 2026 the user requested that paused tasks hide their terminals,
showing task terminals only while In progress. The default Objective filter
excludes every other task status even when selected. Inherited child terminals,
active terminal families and merged children must respect that filter. Task
clicks still open details, but do not create or activate a filtered terminal.
Resuming restores eligibility. Explicit Objective/global Show all controls
remain available, with existing sessions and associations preserved.

This supersedes the selected-task visibility exception in
`selected-task-always-has-visible-terminal.md` and the status-filter bypass in
`active-subterminal-family-stays-visible.md`.
