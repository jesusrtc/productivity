# vs main includes committed and uncommitted files

On October 13, 2026 the user explicitly clarified that vs main is their most
important button: it must show committed differences from main AND all
Uncommitted files together. Use the union of main-to-HEAD, index-to-HEAD and
working-tree-to-index paths, deduplicated. A local reversion to main must stay
visible. Staged edits undone only in the working tree also remain visible.
Collect the current edits during that same refresh; another filter's snapshot
can miss newer work. Retain exact local main, checkout/subfolder isolation,
tracked/nonignored eligibility, paging, and bounded cache workers.

This supersedes the net-diff/exclude-local-reversions guidance in
sidebar-local-main-comparison.md, sidebar-comparison-collects-current-edits.md
and project-sidebar-disk-snapshots.md. Regression invariant: with the same
available checkout and filters, Uncommitted is a subset of vs main.
