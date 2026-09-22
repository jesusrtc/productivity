# Opening an open workspace tab must not rewrite its metadata

`workspaceTabsSetOpen` reads the current saved record, then writes only when
the boolean `tab_open` state changes. A redundant PUT changes workspace.json's
mtime, invalidates file-list data, and triggers expensive sidebar rebuilds in
other clients as well as the active one. Keep the read: an external client may
have closed the workspace since the browser's cached catalog was refreshed.
Actual opens/closes still preserve every other metadata field.
