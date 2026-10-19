# Progress checkpoints and stale WIP alerts

On October 19, 2026 the user approved meaningful progress updates every 20 minutes
and independent alerts after 30 minutes without an agent report. Keep report
freshness separate from process/tool activity; automatic heartbeats must never
refresh the message or imply completion. Preserve the last message, explicit
working/attention/finished semantics, native workspace/Objective-first cards,
active markers and history staying open on notification clicks.

The backend uses one batched supervisor and session-local progress alerts,
with startup/wake grace and one alert per report/turn. A new report resolves it.
Copilot launches add a bundled plugin via --plugin-dir without modifying user
hooks or instruction files. Post-tool reminders cannot interrupt a blocking tool;
the independent monitor still alerts. A final-status hook allows one corrective
continuation, then warns instead of looping. Other providers retain instructions
and the stale monitor. Session incarnation and compare-and-set checks protect
new work from stale scans; a failed process query is never a stopped process.
