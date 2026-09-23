# Terminal clicks open linked documents

Explicit terminal-tab activation opens its linked document inline and highlights
it in Files. Task links select the containing tab and reveal the exact task.
Keep the current workspace and terminal session; opening the document must not
allocate another renderer or start a process. A document link takes precedence
over optional linked-file sync. Polling and passive session restores only update
the sidebar highlight. Ignore stale document fetches after a newer terminal click
or navigation, including selection of an unlinked terminal.
