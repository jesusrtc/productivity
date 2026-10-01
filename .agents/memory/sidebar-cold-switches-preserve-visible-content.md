# Cold folder/worktree switches preserve the visible content

When a selected folder or worktree has no cached view, retain the existing tree,
scroll position, and viewer while the new checkout loads. Show a small loading
indicator on the incoming scope row; keep selection, pins, colors, and metadata
usable. Guard outgoing file actions and viewer interaction until the transition
finishes so they cannot act against the newly selected checkout.

Build project views offscreen and publish the root listing plus recent files in
one DOM update. Capture configuration, exact paths, and navigation generation;
late responses must not steal another selection, including A → B → A. Errors
keep the old view and offer Retry. Preserve a newer document opened by a terminal
while the sidebar was loading. Cached nodes still restore immediately, with no
artificial delay and the existing under-200ms target.

Regression evidence: test_frontend_project_cache.py checks both response orders,
rapid cancellation, stale actions, failed reads/retry, and newer document opens.
test_frontend_scope_switch.py checks 50,000-row cached navigation. The disposable
check_sidebar_comparisons fixture holds real API reads for folders/worktrees and
asserts that the existing tree and viewer remain mounted with a loading icon.
