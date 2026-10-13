# New Current task creates extra terminals

A task can have multiple terminals, with one primary. Explicit **+ New →
Terminal / agent → Current task** must create and select a fresh session of
that requested type, even if the task already has a primary from an automation.
Do not reuse a task terminal before honoring `startFresh` or the requested agent.

Additional sessions inherit the existing primary through the browser's terminal
hierarchy and retain a saved Tasks/Objective association. Do not assign another
`task_id` primary, which would displace the current one. The chosen launch folder
stays unchanged. Normal task navigation still activates the primary, and **Make
primary** lets the user promote another terminal. Browser tests cover repeated
New launches through the real session API while preserving the original primary.
