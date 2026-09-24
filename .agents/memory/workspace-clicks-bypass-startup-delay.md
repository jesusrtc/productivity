# Explicit workspace navigation bypasses startup delays

`selectRepo` defaults to immediate dashboard/sidebar hydration and terminal
restoration. Only initial URL dispatch passes `{initialLoad: true}` to use the
page-startup quiet window. Do not infer that a selection is startup work from
`performance.now() < 2000`: a user may already be clicking visible tabs.

A real Chrome click immediately after tabs appeared took 799–820 ms with the
old 750 ms delay; the isolated candidate took 58–66 ms. Keep remembered document
selection, tab persistence/order, and the active-scope check before terminal
restoration. `scripts/perf/lab_navigation_latency.py` reproduces early clicks
with a CLI-created disposable vault and can compare prior JavaScript via
`--app-revision`. Its small fixture does not establish every UI action's budget.
