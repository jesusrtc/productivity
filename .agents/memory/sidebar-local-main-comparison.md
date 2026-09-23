# Recently updated can compare with local main

The Git quick selectors include separate `vs origin/main` and `vs local main`
choices. The latter uses `refs/heads/main`; the former uses
`refs/remotes/origin/main`. Both compare the selected folder/worktree's working
tree with that exact ref and include only tracked, nonignored files. Do not silently fall back
to the remote branch when local main is missing. Compact labels must distinguish
local from remote, and the selected mode persists in workspace-scoped settings.
