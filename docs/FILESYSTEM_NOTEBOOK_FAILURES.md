# Filesystem and notebook failure investigation

The supplied client logs span September 10–23, 2026. They contain four distinct
failure classes. The client paths are on another machine; its filesystem state,
open descriptors, and notebook code at the time of failure cannot be recovered
from these logs. This checkout's local `errors.log` was empty during inspection.

## Filesystem timeouts and repeated 503s

Both workspace endpoints recursively traversed folders independently. They
followed directory symlinks and reset the depth budget on every Git root, so a
link back to an ancestor checkout bypassed the intended recursion limit.
Each file also incurred repeated stat calls. Concurrent clients could duplicate
the same traversal, and a timed-out caller left its scan running in the shared
four-worker filesystem pool. Session discovery shared that pool and launched
tmux without a subprocess timeout. Once the pool filled, unrelated reads failed
immediately; browser polling amplified the failed requests.

The shared walker now uses scandir metadata, tracks ancestor device/inode pairs,
closes directory iterators before descent, and checks cancellation between
entries. Ordinary linked directories and deep source files remain visible.
Identical in-flight reads share a worker/result until it really exits. tmux
listing has a three-second subprocess timeout and treats failure as unknown,
preserving session metadata. Sidebar fetches share in-flight requests and back
off from two to sixty seconds after failure, independently for each root and
dotfile setting. Filesystem error reporting performs no further filesystem I/O.

A synthetic 10,000-file tree returned identical mtimes with median scan time
reduced from 76.4 ms to 40.6 ms over three runs on this machine. Cycle and
concurrency regressions are covered separately; this timing does not establish
the original client's storage latency or prove it had a symlink cycle.

### Follow-up: a healthy large scan still hit the request deadline

The September 23 05:37 logs came from the first fix (`fsguard.py:213`). Files
and mtime still ran separate traversals of `/Users/jcortes/src/sdui`, and each
had to finish within ten seconds. Cancellation prevented runaway duplicate
work, but also discarded progress through a healthy large tree. Those logs do
not identify a particular slow syscall or establish the size of that checkout.

Both endpoints now use one background snapshot per vault, path, and dotfile
setting. Requests wait at most 150 ms for collection (HTTP overhead and response
serialization are additional). The first slow scan returns 202 with Retry-After;
the browser collects that same job instead of treating it as an empty listing
or starting over. A refresh keeps the last complete result visible with an
"Updating files" status. Polling reuses snapshots for two seconds; explicit file
loads can request a refresh. A revision also detects deletion or replacement
when the greatest mtime did not increase. Notebook running flags stay live
without resolving file paths on request threads.

The scan service permits two workers, no queued jobs, and at most 32 cached
scopes. It is independent of the small-read fsguard pool. Shutdown cancels walks
between syscalls without waiting indefinitely for blocked OS calls. Failed
refreshes retain the last success and retry with exponential backoff. An actual
read stall still returns 503 when no snapshot exists; its response and one
warning identify the workspace root, last operation/path, visited-entry count,
and time without progress. Slow scans that continue progressing are not aborted
at ten seconds. Completed slow scans emit a duration/count info log.

Testing also reproduced a separate recursive-link problem in the default macOS
polling index watcher. Watchdog's normal stat follows nested symlinks; a docs
link back to an ancestor could expand repeatedly and stall watcher shutdown.
The polling watcher now uses lstat to observe the links themselves. Explicit
watch roots are still resolved, and the Files walker still follows linked
folders with ancestor-cycle protection. This removes the reproduced loop; it
does not prove the remote client had that topology.

A controlled HTTP experiment delayed traversal of 275 files past the old
deadline. One scan completed in 13.25 seconds across 38 Files/mtime requests;
the slowest request took 183 ms, responses were only 202/200, and all 275 files
were present in the completed listing. Regression tests cover shared progress,
stalls and recovery, capacity, stale results, cancellation, per-vault/dotfile
isolation, live notebook flags, watcher links, and browser polling. The client
also avoids logging the same failed shared request again for each sidebar
subscriber.

## Large folders and instant scope switching

The background-snapshot fix removed the ten-second failure loop, but ordinary
Files reads still requested a full refresh and mtime polls rescanned every two
seconds. Folder/worktree selection also deleted its previous sidebar payload
and waited for discovery, Git comparisons, and files before rendering. Those
paths explain the persistent updating message and slow switches.

Files now uses a bounded in-memory directory index shared with mtime polling.
Native FSEvents on macOS, inotify on Linux, or Windows notifications invalidate
only affected directory listings and their cached metadata. In-place edits,
creation, deletion, moves, linked targets, and symlink replacement are covered.
Subscriptions are shared, capped at 32, pruned when links disappear, and closed
when roots are evicted or the app stops. There is no per-file kqueue descriptor.
Events during collection remain pending for the next pass; failed collections
retain their invalidations and last complete snapshot.

Healthy native subscriptions reconcile fully every five minutes to catch missed
events; unavailable subscriptions fall back to thirty seconds. Slow scans get
at least four times their previous duration between full reconciliations.
`LAB_WORKSPACE_WATCHER=off` selects that fallback. `refresh=true` explicitly
reconciles everything; ordinary requests reuse the index. Notifications are
debounced and applied when the visible client polls. The existing narrow Lab
metadata watcher remains separate. Filtering on an mtime time window alone
would still enumerate files and miss deletions; parent directory mtimes also
do not identify in-place child edits.

The browser retains up to eight visited sidebar DOM trees, keyed by surface,
workspace, selected folder/worktree, and display settings. Switching restores
nodes, expansion state, scroll, and worktree choices before starting background
requests. Unchanged data does not rebuild the restored tree. The displayed
snapshot revision is compared with polling revisions so scan completion during
navigation cannot leave a stale tree behind. Normal background updates have no
loading banner; initial loading and failures remain visible in small status text.

Validation: Chrome tests switch a 50,000-file cached tree in workspace, Home,
vault, and repository views while background loading is held pending. Measured
switch-to-frame times were 12–21 ms locally, below the requested 200 ms budget.
The checks include actual worktree select changes, DOM identity, preserved open
folders, filter isolation, and cache limits. A separate 20,000-file / 501-directory
fixture reread one directory after an edit and zero on a cached traversal.
Unit and native-event tests cover incremental updates, moves, symlink targets,
overflow, failed scans, fallback scheduling, shared watches, and cleanup.

These are local fixture measurements, not a measurement of the remote SDUI
checkout. First visits still require an initial scan; caches are in memory and
rebuild after a server/browser restart. The implementation has no project-name
or repository-size special cases.

## File-descriptor exhaustion and cascading 500s

`EMFILE` from ordinary JSON reads, `os.pipe`, and Jupyter socket creation proves
process-wide descriptor exhaustion, not corrupt workspace metadata. The existing
terminal metadata fix explicitly closes SQLite connections rather than relying
on SQLite's transaction context manager or garbage collection. Its tests retain
connection references and verify closure on success and query failure.

An additional leak remained when Jupyter opened client channels but failed its
readiness check: only the manager was shut down. Startup and restart failures
now stop channels and clean manager resources. Notebook failures also clear
in-memory running state when persisting their error fails (including EMFILE).
The original descriptor inventory is unavailable, so attributing every leaked
descriptor in those historical logs to either path would be speculative.

## Notebook execution deadlines

The 300/600/1200/1800-second 504s match execution deadlines. A silent dead kernel
previously consumed the whole deadline, and a timed-out kernel that ignored its
interrupt could block later cells again. Execution now checks kernel liveness
after empty IOPub polls. On timeout, it waits up to two seconds for that run's
idle acknowledgement; an unresponsive kernel is closed and the next execution
starts a fresh one. A responsive interrupted kernel retains its Python state.

Real-kernel tests cover sleep timeout, retained state, process exit, and successful
execution afterward. A healthy cell exceeding the caller's time limit still
returns 504. The logs alone do not show whether the historical cells were slow,
blocked in their libraries, or running in a dead/unresponsive kernel.

## Plotly initialization

The notebook loader detected `require(["plotly"], ...)` but missed HTML outputs
calling `Plotly.newPlot(...)` directly. Those scripts ran before the lazy-loaded
library existed. Both notebook viewers now recognize direct and AMD calls and
wait before activation. A failed load leaves scripts dormant and shows a visible
error; lazy asset failures can be retried. Repeated activation preserves existing
charts and their interaction state.

Chrome coverage exercises direct HTML, native MIME, saved/live outputs, duplicate
views, typed arrays, zoom, a failed dependency load and retry, and concurrent
activation using the vendored library without external network requests.

## Applying the fix on the client

Update the framework checkout on the affected client to the fixed `origin/main`,
restart that Lab server when its running work can be stopped, and reload the
browser to load the updated JavaScript. Restart also releases descriptors held
by the old process. Historical error entries are retained; the relevant check
is whether new entries recur after that deployment.
