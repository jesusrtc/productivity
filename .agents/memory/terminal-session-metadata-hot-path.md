# Terminal session metadata stays off the global poll

`GET /api/term/sessions` without a project is polled every five seconds by
the top tabs/dashboard, which do not consume provider titles, latest tasks,
or captured-pane summaries. Keep agent enrichment disabled on that unscoped
path (and the attach-picker scan); only project-scoped terminal lists need the
details.

When caching Codex TTY-to-thread metadata, record every TTY inspected—not only
the TTYs that resolved. Plain terminals and idle panes are valid cache misses;
omitting them from cache coverage makes every mixed-terminal lookup cold.

