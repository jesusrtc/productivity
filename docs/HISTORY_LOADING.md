# Progressive Git history

The shared file/repository history modal prioritizes uncommitted changes and
loads commits independently. File status uses a scoped porcelain status read;
it does not construct patches or wait for `git log`. Repository history shows
Working tree and the base comparison immediately and fetches each patch only
when selected. Base comparisons never block the initial view.

The first commit page contains at most 20 entries from the last 60 days. Scrolling
near the bottom or selecting Load more fetches another page. Once that window is
exhausted, Load commits older than 60 days expands it without resetting the
selected revision. Appending commits preserves the active diff, list position,
and revision focus. Errors retain loaded entries and expose a retry. Closing or
switching the modal aborts outstanding browser requests; Git commands remain
bounded by their server-side timeouts.

`/api/workspace-entry/history` supports `phase=working-tree|commits|all`, `limit`,
`offset`, `since` (Unix timestamp; zero means all dates), and `revision` (Git SHA).
The response includes `next_offset`, `has_more`, `can_load_older`, and the resolved
`revision`. The modal pins that revision and cutoff while paging, so concurrent
commits do not shift offsets. The default `all` phase remains compatible with
existing callers. File `.` selects the root for this read endpoint only; generic
explorer mutation guards continue to reject root rename/delete.

Git's `--skip` with `--follow` can bypass rename processing and omit history
before the rename. File pages therefore replay the bounded prefix and slice the
result; directory/repository pages use native skip. The recent window uses
`--since`, which stops traversal at the time boundary. Older history stays
available in additional pages; it is never exhaustively prefetched.

Real-Git tests cover status without log/patch generation, mixed local states,
unborn repositories, empty recent windows, renames across page boundaries, and
HEAD changing during pagination. Chrome tests hold commit requests pending while
local diffs render, then verify pagination, retries, scrolling, selection,
cancellation, and lazy base comparisons. Those controlled tests demonstrate
request independence; they do not measure the user's large repository.
