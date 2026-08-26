# Recent files use a compact folder tree

The recently updated sidebar section mirrors file hierarchy instead of showing
flat paths. Folder chains with no files and exactly one child collapse into one
row (for example `src/core`), while genuine branch points remain separate
(for example sibling `src/core` and `tests` rows below `core`). Recent folders
are collapsible and remember their open state through the shared tree-state
storage.
