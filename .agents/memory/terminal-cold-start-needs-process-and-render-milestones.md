# Separate shell startup, parsing and rendering during cold creation

Terminal creation's configured owned echo shell has a real cold-start cost.
In an untraced 20-creation run, its first existing PID/cwd record was written
219.7 ms after the click, before tty setup and initial output; complete
creation took 269.0 ms. Later records appeared after 52.5–84.7 ms. This is a
pre-output milestone, not the actual first-byte timestamp or pure CPU time.
Do not replace/accelerate the fixture workload or omit the first sample to
claim the full creation target. Browser paint alone is not the entire delay.

With LAB_PERF_TRACE, the terminal probe records parse, render and changes to
readiness predicates. Normal runs add no parser listener or diagnostic timeline.
Keep rendered-text/focus/selection/scope checks unchanged. Diagnostics cap each
pane at 1,000 detail records and explicitly count overflow; require zero dropped
stages plus trace/profile time coverage and no trace data loss before deriving
event order. The creation fixture reads the existing process file's mtime only
during cleanup, without adding work to the shell or measured click path.

Details and both traced/untraced failures are in performance-progress.md.
