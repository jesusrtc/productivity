# Worktree pull/rebase arrow

The user requested a down-arrow on worktree rows on October 7, 2026 to pull and
rebase from master. Place it beside the existing Terminal control, enable only
the selected worktree, and fetch origin/master before rebasing its feature
branch onto the fetched commit. Do not switch branches, push, rewrite sibling
branch refs or silently substitute main when remote master is missing.

Use Git autostash for local tracked edits, retain rebase/autostash conflicts,
and show the output with continue/abort guidance only for a paused rebase.
Restrict the endpoint to admin-approved linked checkouts. Prevent overlapping
updates across linked worktrees and browsers, refuse unfinished Git operations,
and recheck the branch after fetching. Browser completion must retain the
captured checkout and avoid refreshing a different scope after navigation.
