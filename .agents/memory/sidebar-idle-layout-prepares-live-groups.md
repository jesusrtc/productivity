# Prepare large sidebar groups without a single forced-layout pause

Recent-file groups start with content-visibility:auto. After mounting, prepare one
open group per requestIdleCallback and mark only the live element with
`data-sidebar-layout-ready`, switching its content visibility to visible. Native
find/browser extraction can then inspect them without forcing the entire skipped
tree to lay out in one task. This spreads work; it does not promise less total CPU.
The original flex rows, adaptive heights, complete DOM and accessibility remain.

Keep the marker as an attribute: anonymous flat groups use their class as their
reconciliation key. Never decorate cached templates. Cancel prior jobs and release
their group/first/last references on replacement; verify mounted first/last/count,
connection and page visibility before each callback. Skip closed groups and
containers above 200 direct children. Resume on visibility and folder expansion.

Prepared groups made sidebar drags much slower until their layout was invalidated
at drag start. Reset markers/cancel jobs before sidebar or window width changes,
suppress preparation during dragging, and resume after release. The native resize
probe (`lab_navigation_latency.py --resize`) catches this regression.

Trace from before Page.navigate and retain buffered long tasks, including work
before the echo terminal is ready. Quiet typing passed 50 ms in the measured
large nested/flat cases, but changing-file typing still missed; this is not a
universal latency guarantee or proof of iTerm parity.
