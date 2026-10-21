# Automation reconnects use three spaced attempts before a red alert

On October 21, 2026 the user requested automatic reconnection when automation
connections disconnect: up to three attempts, every two minutes, and a red
notification only after all three fail. Reuse the automation's own configured
launch spacing between commands for initial launch, manual reconnect, merged
renewal and automatic batches; default five seconds. Preserve tab identities,
original saved commands and prior logs. This supersedes the explicit-only rule
in automation-recovery-only-for-stopped-work.md.

Default scope is SSH/tmux/Mosh connections, wrappers observed launching them,
and services with a configured health check. Finite local commands remain manual.
Confirm each attempt after 30 seconds, preserve uncertainty, and never kill live
manual work or replay paused/completed, closed, replaced or ambiguous panes.
Persist retries/deadlines across backend/browser restarts with no catch-up burst.
One red card belongs to the closest main and offers exact-generation Reconnect;
keep actual agent status and history. Manual recovery starts a fresh budget.
