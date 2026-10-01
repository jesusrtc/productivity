# Workspace terminals choose their folder before launch

Every new workspace terminal asks for its launch folder, offering the workspace
root and that workspace's pinned folders and exact worktrees. Ask even when only
the workspace is available, for the first automatic launch, and when creating a
terminal from a file. Cancel or navigation must create nothing. Existing saved
terminals restore their original folder without asking again.

The chosen folder stays fixed for that terminal. Remove folder reassignment and
unlink controls, reject folder changes through metadata and restore APIs, and
keep file/document/task associations independent of the launch folder. Store
cwd durably. Fresh terminals reserve stopped sessions' logical names too, so
they receive a new UUID and cannot overwrite an older conversation or folder.

This supersedes the editable code-scope association and file-to-scope cascade
in document-terminal-independent-code-scope.md. File and document links still
preserve the shared terminal owner, name, conversation and process.
