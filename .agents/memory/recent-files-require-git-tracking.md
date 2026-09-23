# Recently updated requires Git tracking

All Recently updated scopes exclude untracked and Git-ignored files; the normal
Files view retains them. Time scopes use git_tracked on workspace snapshots,
computed per nested repository/worktree with NUL-separated Git index paths minus
Git ignore matches. Staged additions qualify; non-Git projects have no recent
entries. Git comparisons also filter their paths by this membership. Snapshot
revisions include membership and watch Git metadata outside linked worktrees,
so staging or ignore edits refresh recent results without changing file mtimes.
