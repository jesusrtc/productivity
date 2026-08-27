# Sidebar file scopes can follow worktrees

File-view settings may hold a browser-local parent directory. Only direct child
folders registered by Git as worktrees of the active repository are offered;
never treat every folder under that parent as a worktree. When a project is a
subdirectory of the main checkout, preserve its relative path in each linked
worktree. Discovery caches must vary by both parent folder and active base root.
Each sidebar surface remembers its own Root/worktree selection, and both
Recently updated and Files must use that same selected root.

Projects may be non-Git wrapper folders with registered repositories nested
inside them. Keep `main` file browsing rooted at the wrapper, but anchor Git
worktree discovery and repository history to the project's first registered
repository instead of the wrapper's nearest enclosing repository.

Worktree colors are browser-local, default to `#6e7681`, and appear as the
vertical scope rail around those sections. Keep notebook APIs pinned to the
active workspace root even when ordinary file browsing uses another worktree.
