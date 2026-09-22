# Document terminals

Opening a task or document makes its agent terminal available. All of the
content tabs share that document's conversation. Reopening resumes the exact
saved provider conversation; it never selects whichever chat was most recent.
The document path and selected tab are supplied as context. Opening alone sends
no task to the agent and makes no edits to document content.

Defaults keep one idle terminal ready and put hidden idle terminals to sleep
after five minutes, or earlier when another document needs the idle slot.
Sleeping releases the managed process. Conversation bookmarks remain on disk;
the 36-hour cleanup applies only to unused bookmarks without conversation or
submitted input. Existing provider conversation IDs and histories are retained.

Working agents, approval waits, unknown work and unsent input are protected.
An attached terminal stays ready. Unsent text keeps its process alive until
submission; saved conversation history resumes after process sleep. The browser
keeps only the visible document's xterm renderer and WebSocket.

There is no three-document active-process cutoff. Before launching, Lab checks
OS memory headroom and reserves the larger of 1 GiB or 15 percent of RAM, plus
512 MiB per process launched during the preceding ten seconds. Low memory first
reclaims eligible idle processes, then delays the new launch if necessary. The
terminal displays a waiting state and retries every 30 seconds while visible.
If memory cannot be measured, it waits instead of launching unchecked. Existing
work continues. This is admission control, not an OS limit on memory used by
already-running agents or unrelated applications.

Settings are under Global → Documents. The existing `maxRunning` JSON key is
retained for compatibility but now means **Idle terminals to keep ready**. Saved
values remain effective as idle-cache budgets. The UI describes the new meaning.
`sleepMinutes` controls hidden idle timeout; `expireHours` removes only unused
bookmarks. The new defaults are 5 minutes, 36 hours and 1 idle terminal. Existing
explicit settings are preserved. No Assistant data migration is needed.

Missing or exited tmux sessions are reconciled during opening, status checks
and cleanup. Exact session identity and process ownership are verified before
retirement. Browser closure, tab switching and polling never submit agent work.
