# Watched notifications follow current working status

On October 21, 2026 the user reported a pinned green finish beside a yellow WIP
terminal. Preserve the last notification text and exact close/report identity,
but display yellow Working with an ellipsis while the terminal is working,
including immediate feedback after submitting an LLM message. Mark retained text
as Last notification. Active progress, recovery and automation warnings retain
their own status. Closed/history-only events keep their original event status;
presentation must never mutate agent reports or task completion.
