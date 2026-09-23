# Workspace document references

Assistant documents can be dragged onto real workspace tabs or the Documents
sidebar section above Recently updated. References live in each workspace at
`.lab/document-links.json`, keyed by Assistant root and immutable document ID.
Do not copy or move the Markdown source. Resolve the current title/path on read.

Existing linked sessions owned elsewhere appear under Document terminals, with
`document_source` preserving their canonical vault/workspace/logical name.
Viewing/dragging never creates a process or changes cwd. Workspace terminal drops
create the same document/task link used by the modal. In a workspace, unlinking
asks Keep in workspace or Move to Assistant; transfer metadata and UUID ownership
atomically without stopping the session, losing the conversation, or clearing
file/folder links. Legacy tmux names need ownership aliases/tombstones to prevent
old registries from re-adopting transferred terminals.

The document modal remembers Right/Bottom terminal placement per document in
browser storage. A workspace reference can be removed independently of terminal
links. The same document may be referenced by multiple workspaces.
