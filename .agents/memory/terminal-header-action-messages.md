# Floating terminal messages follow reported status

The user clarified on October 15, 2026 that terminal notifications must be
floating red/green cards in a top-right stack, like toast notifications. They
overlay the interface without reserving console space and stay visible with
the terminal panel closed. This replaces the initial inline header design. Red attention requests stay until the terminal status changes, including
immediate yellow after submitted LLM input. Clicking red opens its owning vault,
workspace, Objective and exact terminal without dismissing it. Green finished
messages expire five minutes after the report timestamp, or disappear with the
shared green acknowledgement on click. Expiry must not clear terminal/workspace
status, and reloads must not reset the expiry. No desktop notifications or separate popup windows.

Use the existing batched report feed, deduplicate borrowed document terminals,
retain original ownership, and guard clicks by socket/session incarnation plus
report ID. Home, Assistant and workspace dots prioritize red, yellow, then green.
Failed or stale navigation must not review a report. UI commands expose the same
message list and exact navigation; no agent instruction changes are needed.
