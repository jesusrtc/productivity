# Worktree choices refresh without reloading

The visible file-worktree picker rescans its configured parent every five
seconds and when Lab regains focus or visibility. Worktrees can live outside
the selected folder, so file mtime polling cannot drive discovery. Update only
changed options, preserve the selected worktree and open document, share
in-flight scans, and keep cached choices on transient errors. Ignore responses
after navigation and pause background refresh during document editing.
