# Linked file terminals separate durable links from browser sync

A file-to-terminal link is durable project session metadata (`linked_file` with
`root` and `path`), and the terminal's display label is the file basename.
File double-click remains the full-size file modal; linking starts from the
file's secondary-click menu. Automatic file-to-terminal and terminal-to-file
navigation is controlled separately by the browser-local `Sync linked` switch,
which defaults off, so links remain useful without forcing navigation.
