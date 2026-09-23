# Document drags paste the absolute source path into terminals

The user wants sidebar Documents rows to behave like ordinary file rows when
dropped inside a terminal: paste the absolute Markdown source path, shell-quote
it when needed, and never submit it. Use the document's Assistant root and
resolved source path, not its title or the active workspace root.

Keep both drag payloads: the document identity still links it when dropped onto
a workspace, while the file-path payload uses the existing xterm paste handler
inside the console. This also applies to Assistant Linked documents and document
cards. Unlink buttons and missing documents must not become drag sources.
