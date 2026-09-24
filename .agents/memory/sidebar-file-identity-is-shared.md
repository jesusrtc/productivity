# Sidebar file actions share one row identity

Normal workspace, self/vault and Recently updated rows use `data-open-file`,
`data-filepath` and `data-entry-root` for opening, explorer context, dragging,
terminal-link drops and linked-file reveal. Do not restore duplicate
`data-entry-kind="file"` / `data-entry-path` attributes on those rows: large
sidebars parse and clone that repeated metadata on the cold path.

Repository trees, folders, pinned shortcuts and instruction rows still use
their explicit entry-kind/path metadata. The context helper gives that metadata
precedence and preserves existing root fallback. Virtual/server/external rows
without either opt-in must remain excluded. Keep explicit captured roots so
worktree or vault changes cannot reinterpret a retained row.

Browser coverage verifies native context clicks and copy-mode drag payloads,
quoted/Unicode paths, terminal-link drop/reveal, geometry and pristine clones.
