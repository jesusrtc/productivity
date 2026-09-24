# Performance goal stopped at a stable main checkpoint

On September 23, 2026, the user explicitly requested stopping the ongoing latency
goal as soon as a stable checkpoint could be pushed to main. Stop additional
optimization and experiments; finish only the checkpoint integration, validation,
and push. Do not resume this latency goal without a new explicit user request.

The stopped goal is not a claim that every action meets 200 ms, terminal typing
always meets 50 ms, or physical iTerm parity has been established. The unresolved
measurements remain documented in docs/performance-progress.md.
