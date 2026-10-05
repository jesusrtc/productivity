# Copilot status follows the live foreground conversation

The client supplied Copilot CLI 1.0.91 evidence on 2026-10-05: autopilot can
finish with an empty assistant message requesting `task_complete`, followed
by `session.task_complete`, without a final text response. Accept completion
only for boolean `success: true` with an absent or `completed` outcome.
Tool execution success alone is insufficient; `blocked` waits and rejection
keeps working. Ordinary text replies still require their matching turn end.

Resolve the exact Copilot PID on the requested terminal TTY, its current-process
log's foreground registration, and its matching `inuse.<pid>.lock` marker.
Conversation switches invalidate saved launch IDs. Never substitute a recent
or same-directory transcript when live identity is unavailable. Keep discovery
TTY-scoped, cached, and bounded. Tests use the client-supplied fixture and
isolated mocked process/log state; never send input to live user sessions.
