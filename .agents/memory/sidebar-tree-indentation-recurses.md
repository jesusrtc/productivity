---
name: sidebar-tree-indentation-recurses
description: "Sidebar indentation must scale with arbitrary folder depth"
metadata:
  type: project
---

Lab file trees can be arbitrarily deep. Indentation and guide CSS must recurse
through `.sidebar-folder-children` containers rather than enumerate selectors
for levels one, two, three, and so on. A hard-coded ladder previously capped
indentation after three levels, making `lab/`, `commands/`, and its files appear
at the same horizontal position.

Each nested children container now contributes one 16px indentation step. Its
guide uses the same relative position at every level, so nesting supplies the
additional offset automatically.
