# Notification arrival paints before graphics setup

On October 16, 2026, a real Home notification click measured 271–582 ms on
first opening a terminal, while subsequent clicks were 50–114 ms. Terminal
listing was only 20–45 ms; synchronous xterm WebGL atlas/shader initialization
dominated the cold attach. Notification activation now passes `deferWebgl`
through `_termActivateTab` to `termAttach`: connect at the fitted geometry,
paint real output with the DOM renderer, then initialize WebGL after paint in
browser idle time. Cached live panes schedule the same handoff immediately
after showing their existing output. Ordinary tab clicks keep their policy.

Do not replace fresh incarnation checks with a name-only cached lookup to
meet a latency target. Keep exact workspace/Objective/task/asset navigation,
red persistence, report-ID-safe green review and destination cues. Deferred
GPU work must be deduplicated and canceled on parking/disposal, and must never
activate on another pane. Verify actual Chrome click-to-visible-output/focus,
including the first uncached pane, rather than just selected-tab state.

DOM and WebGL round cell widths differently in the vendored xterm. After the
handoff, fit once and send a resize only if the grid changes; never clear the
buffer or inject input. The real-Chrome lifecycle regression verifies the fitted
grid, retained output/focus and GPU failure fallback. The reusable
`scripts/perf/lab_notification_latency.py` probe measured 24 real Home attention
clicks across three private profiles at 40–184 ms (p95 118 ms), with all three
uncached opens at 78–118 ms. It never sends terminal input or changes agent reports.
