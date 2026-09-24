# File rows share their existing path/root metadata

Normal workspace, self/vault, and recent-file rows opt into sidebar-level click
and double-click handling with `data-open-file`. Use escaped `data-filepath` and
`data-entry-root` values for document/modal/history operations. History controls
stop the file action on both click and double-click; other inline controls stop
propagation themselves. Pinned and instruction shortcuts retain their distinct
handlers. Test quoted and Unicode names and fresh template clones.

Context, drag and terminal-link consumers also accept this same identity;
see [the shared-identity contract](sidebar-file-identity-is-shared.md). Ordinary
rows do not need a second entry-kind/path copy. Legacy explicit entry rows keep
their existing behavior.
