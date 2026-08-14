# Terminal tab dividers are browser-local

Colored terminal-tab dividers are navigation chrome. Persist them in browser
storage, scoped by workspace plus Home/workspace/project terminal surface; do
not write them into project or workspace metadata.

A divider is only a draggable colored line in the session order. It has no
name, count, fold state, container chrome, active-header marker, or per-tab
stripe. Clicking the line opens its color/delete menu, and `+ Divider` inserts
one immediately before the active terminal tab. Do not restore group UI or
per-tab group-assignment buttons; terminal tabs are renamed by double-click.
