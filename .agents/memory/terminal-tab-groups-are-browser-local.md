# Terminal tab dividers are browser-local

Colored terminal-tab dividers are navigation chrome. Persist them in browser
storage, scoped by vault plus Home/vault/workspace terminal surface; do
not write them into workspace or vault metadata.

A divider is a draggable colored line in the session order. Clicking or
secondary-clicking the line opens its color/delete menu. Secondary-clicking
a tab adds a divider above/below it (before/after in horizontal mode).

As requested on 2026-09-08, named collapsible groups now coexist with dividers.
Their `tabGroups` and `tabMembership` fields share the same scoped browser
storage, separately from legacy divider migration fields. Tabs can be renamed
by double-click or through the context menu.
