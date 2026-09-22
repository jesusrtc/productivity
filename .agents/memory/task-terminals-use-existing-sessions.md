# Task terminals link to existing sessions

The client prefers controlling the number of terminals explicitly. Opening a
task/document must never create or automatically resume a process. Drag a
terminal tab onto a document row; inside the modal, Link terminal offers
existing sessions that can be dragged onto JSON task/subtask rows or selected
by click. Preserve the same process, conversation, unsent draft and cwd.

Keep one durable linked_task association per terminal and one terminal owner
per task/document. Task IDs are independent of content-tab IDs. Transfers and
unlinking never kill sessions and preserve independent file/folder links.
Show stopped links without restarting them. Previous managed conversations
remain saved and can be explicitly resumed; their old idle policy is separate.

Home metadata is shared across vaults while runtime registrations can live in
different roots: resolve all runtime registries before deduplicating Home.
Never allocate session UUIDs or start a process during link discovery.
