# Sidebar shortcuts preserve the file tree

Pinned and recently updated sidebar sections are shortcut views. A file shown
in either section must also remain in its original folder in the normal tree;
never filter shortcut entries out of the tree.

The shared file-view controls persist browser-locally per workspace and cover
hidden files, recent file freshness, and optional extension filtering.
`/api/workspace-files` exposes `mtime` for every regular file so recent-file
filtering can remain client-side.
