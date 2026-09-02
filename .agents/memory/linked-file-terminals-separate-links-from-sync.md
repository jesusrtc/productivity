# Linked file terminals separate durable links from browser sync

A file-to-terminal link is durable project session metadata (`linked_file` with
`root` and `path`), and the terminal's display label is the file basename.
File double-click remains the full-size file modal; linking starts from the
file's secondary-click menu. Automatic file-to-terminal and terminal-to-file
navigation is controlled separately by the browser-local `Sync linked` switch,
which defaults off, so links remain useful without forcing navigation.
Sync is edge-triggered, not continuously enforced: only clicking a filename in
Files/Recently Updated may select its terminal, and only clicking a terminal
pill may open its file. Generic file opens, refreshes, restores, pinned/meta
shortcuts, and context-menu Open must never trigger the reverse link. A newer
explicit file or terminal choice cancels any older linked-file navigation still
in flight. Terminal-to-file focus prefers Recently Updated, then Files.
Completing either a new-terminal or existing-terminal link also copies the
file's absolute path to the clipboard so it can be pasted into an agent prompt.
