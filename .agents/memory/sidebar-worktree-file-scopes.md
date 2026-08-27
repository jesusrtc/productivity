# Sidebar file scopes can follow worktrees

File-view settings may hold a browser-local parent directory whose direct child
folders are offered as worktree roots. Each sidebar surface remembers its own
Root/worktree selection, and both Recently updated and Files must use that same
selected root.

Worktree colors are browser-local, default to `#6e7681`, and appear as the
vertical scope rail around those sections. Keep notebook APIs pinned to the
active workspace root even when ordinary file browsing uses another worktree.
