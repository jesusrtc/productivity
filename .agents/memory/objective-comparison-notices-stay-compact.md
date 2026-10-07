# Objective comparison notices stay compact

When assigned worktrees cannot provide the selected recent-file Git comparison,
show one compact, explicitly sized notice, not raw text and an empty worktree
heading for every scope. Keep successful checkout-owned file results visible.
Omit empty groups; an entirely empty union has one quiet no-matching-files
message. Recent scope headings with files use compact, truncated names and
retain full names in their tooltip. Preserve paging and stale-response guards.

The local-main selector compares with refs/heads/main and intentionally does
not substitute origin/main. Missing local main or a non-Git scope can return
available=false. Explain alternate Uncommitted/time filters without silently
changing the user's selected comparison or repository branches.
