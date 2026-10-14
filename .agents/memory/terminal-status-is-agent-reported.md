# Terminal status is explicitly reported by the agent

The user’s October 14, 2026 preference replaces output/quiet-period and provider
completion estimation for terminal indicators. Use `lab notifications working`,
`attention`, or `finished`, with optional hover text, from the calling Lab tmux
pane. These set a steady yellow, pulsing red, or blinking green dot, respectively.
They send no desktop notifications, pop-ups, sounds or external messages.

Only finished clears on a deliberate tab/green-dot click. Working and attention
require another explicit agent report; new work replaces an old finished report.
Hover, elapsed time, output, focus and connection changes never change the state.
The launch context and `lab context` require reporting on start/resume, before
needed input/review, and before a completed final response. Status never changes
task/checklist completion. Unreported terminals have no dot.

Reports live in the session-local `@lab_status` tmux option, encoded as bounded
JSON/base64, and travel in the existing batched listing. Resolve TMUX’s exact
socket and TMUX_PANE, then target its tmux session ID; never guess from browser
selection or the socket used for new launches. Browser acknowledgements are
keyed by socket/session incarnation and shared within the same browser profile.
Workspace indicators prioritize attention, then working, then finished.

This supersedes the status inference in terminal-activity-verifies-content.md
and terminal-output-quiet-period-and-review.md; explicit green-click review is
retained. Native tests must use isolated disposable tmux sessions and browsers.
