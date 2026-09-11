# Daily feature usage

In Home → Logs → Feature usage, select a local calendar date or All days.
Rows show `date  feature name - usage count`, sorted by newest date, then
highest usage count, with alphabetical ties. Copy copies the displayed rows.
Clear removes all recorded feature counts across registered vaults, including
other dates. Diagnostic log history is independent.

Counters begin when this instrumentation is installed; raw historical clicks
cannot reliably establish completed actions and are not backfilled.

Tracked actions:

- Workspace creation from the tab + button or vault overview; workspace rename.
- Terminal links to documents, folders, and worktrees, separating secondary
  click, drag and drop, and the folder link button. A document's inherited
  folder association does not produce a second count.
- Removing document/folder links, including the terminal selection menu.
- Creating shell or agent terminals, attaching external terminals, closing
  selected terminals, grouping/ungrouping tabs, and moving tabs/dividers.
- Creating files, folders, and notebooks; renaming and deleting files/folders.
- Enabling/disabling Focus, Keep Alive, and linked terminal sync.

Counts represent completed user operations, not menu opens, canceled dialogs,
failed API requests, background polling, or restored sessions. Grouping counts
one group operation; batch closes/unlinks count each successfully changed
terminal. No document paths, names, terminal content, or user identifiers are
included. Dates use the browser's local calendar at completion. Uploads are
best effort and use keepalive; network loss can prevent an event arriving.

The browser calls `window.labFeatureUsage(featureName)` at the successful
operation boundary. New instrumentation should use a stable, human-readable
name, preserve the initiating method across asynchronous dialogs, and avoid
counting the same action through both generic clicks and semantic callbacks.

`POST /api/log/usage` increments one `{day: "YYYY-MM-DD", feature: "..."}`.
`GET /api/log/usage?day=YYYY-MM-DD` returns daily totals across registered
vaults (omit `day` for all dates). `DELETE /api/log/usage` clears the counters.
Reading and clearing require admin access; ingestion requires authentication.
Each vault stores `feature-usage.sqlite3` beside its logs. Atomic SQLite
increments persist independently of log rotation and the diagnostic event
rate limiter; every database handle is explicitly closed.
