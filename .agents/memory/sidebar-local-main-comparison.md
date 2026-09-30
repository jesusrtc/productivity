# Recently updated can compare with local main

The Git quick selectors are `Uncommitted` and `vs local main`. The latter uses
`refs/heads/main` and compares the selected folder/worktree's complete working
tree, including staged and unstaged changes, with that exact ref. Both include
only tracked, nonignored files. Do not silently fall back to the remote branch
when local main is missing. The selected mode persists in workspace-scoped
settings.

On September 30, the user removed `vs origin/main` and `Last 2 commits` because
their cost was unnecessary. Remove them from both quick selectors and settings;
old saved selections migrate to `local-main`.
