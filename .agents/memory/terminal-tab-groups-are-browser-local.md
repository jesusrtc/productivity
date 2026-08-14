# Terminal tab groups are browser-local

Named, colored, collapsible terminal-tab groups are navigation chrome. Persist
them in browser storage, scoped by workspace plus Home/workspace/project
terminal surface; do not write them into project or workspace metadata.

Groups use an ordered-divider model: a group tab starts a group, and every
terminal tab after it belongs to that group until the next group divider.
Dragging either tabs or dividers changes membership implicitly. Do not restore
per-tab group-assignment buttons; terminal tabs are renamed by double-click.
