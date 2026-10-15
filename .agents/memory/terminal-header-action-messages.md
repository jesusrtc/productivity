# Terminal header messages follow reported status

The user requested in-app messages beneath the terminal header on October 15,
2026. Red attention requests stay until the terminal status changes, including
immediate yellow after submitted LLM input. Clicking red opens its owning vault,
workspace, Objective and exact terminal without dismissing it. Green finished
messages expire five minutes after the report timestamp, or disappear with the
shared green acknowledgement on click. Expiry must not clear terminal/workspace
status, and reloads must not reset the expiry. No desktop notifications or pop-ups.

Use the existing batched report feed, deduplicate borrowed document terminals,
retain original ownership, and guard clicks by socket/session incarnation plus
report ID. Home, Assistant and workspace dots prioritize red, yellow, then green.
Failed or stale navigation must not review a report. UI commands expose the same
message list and exact navigation; no agent instruction changes are needed.
