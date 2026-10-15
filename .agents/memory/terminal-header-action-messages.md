# Floating terminal messages follow reported status

The user clarified on October 15, 2026 that terminal notifications must be
floating red/green cards in a top-right stack, like toast notifications. They
overlay the interface without reserving console space and stay visible with
the terminal panel closed. This replaces the initial inline header design. Red attention requests stay until the terminal status changes, including
immediate yellow after submitted LLM input. Clicking red opens its owning vault,
workspace, Objective and exact terminal without dismissing it. Green finished
messages stay until reviewed by click or replaced by a newer terminal status,
including across reloads. The user explicitly removed the earlier five-minute
expiry. Clicking green uses the shared acknowledgement to clear the message
and indicators together. No desktop notifications or separate popup windows.

Clicking either card must make its destination obvious: reveal and scroll the
exact tab into view, then pulse its background and outline three times. The
selected blue outline alone was insufficient. Expand a collapsed group or show
all terminals in the selected Objective when needed. Reduced motion uses a
brief steady highlight. Apply the cue after acknowledgement rerenders and keep
its original deadline through subsequent rail rerenders; repeated clicks restart it.

Use the existing batched report feed, deduplicate borrowed document terminals,
retain original ownership, and guard clicks by socket/session incarnation plus
report ID. Home, Assistant and workspace dots prioritize red, yellow, then green.
Failed or stale navigation must not review a report. UI commands expose the same
message list and exact navigation; no agent instruction changes are needed.

Notification and terminal-tab clicks now share task-and-asset navigation: select
the owning task/subtask, then open its linked asset while keeping Task assets
accessible. Resolve asset-only task assignments without reassigning the session.
Explicit ownership still wins over an asset in another Objective. Keep the exact
notifying terminal, including inherited children and secondary sessions, rather
than switching to the primary. See terminal-clicks-open-task-assets.md for the
updated navigation contract and browser regression coverage.
