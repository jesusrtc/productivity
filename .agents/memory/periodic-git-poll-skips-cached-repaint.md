# The periodic Git poll refreshes data without repainting the old cache first

The six-second sidebar Git timer operates on already mounted, decorated rows.
Call `_sidebarGitStatusRefresh({repaint: false})` there: reapplying cached status
before a freshness check/fetch duplicated a 7.7–13.3 ms traversal in the large
native fixture. The measured callback fell to 0.013–0.179 ms without changing
polling, fetch-floor, in-flight or workspace/worktree response guards.

Keep the helper's default cached repaint for newly rebuilt rows. Fresh responses
still apply current status once; a late old-root response updates only its cache.
Do not infer whole-run typing gains from this small callback change: shared tmux
output bursts and browser stalls remain separately measured.
