# Large project sidebar measurements

Measured September 23, 2026 on this Mac, using real checkouts of all six requested
repositories and a full linked worktree for each. Cached project/worktree
navigation, Uncommitted, vs local main, and recent history all measured below
500 ms. The first uncached Linux and LLVM scope openings still exceeded that
budget. This is not a claim that every first visit or every machine meets 500 ms.

## Results

Maximum observed milliseconds in the two repeat browser rounds, across both
the checkout and its linked worktree:

| Repository | Tracked paths¹ | Project/worktree² | Uncommitted | vs local main | Recent commits |
| --- | ---: | ---: | ---: | ---: | ---: |
| torvalds/linux | 96,041 | 100 | 36 | 32 | 49 |
| llvm/llvm-project | 185,249 | 114 | 32 | 33 | 48 |
| kubernetes/kubernetes | 31,394 | 364 | 35 | 31 | 200 |
| python/cpython | 6,380 | 165 | 33 | 34 | 231 |
| rust-lang/rust | 63,125 | 160 | 34 | 33 | 52 |
| git/git | 4,855 | 143 | 32 | 37 | 109 |

¹ Includes three fixture paths used to verify committed, staged, and unstaged
changes. These are full file checkouts, with shallow upstream history of 25
commits and two additional fixture commits. Upstream revision IDs are in
[http.json](http.json). Linux reported case-colliding paths on this Mac's
case-insensitive filesystem; the index contains them, but not every colliding
pair can exist independently on disk.

² Scope readiness requires both the directory rows and the correct local-main
comparison rows, including the staged and unstaged fixture paths. Worktree
dropdown input is a DOM `change` event, labelled `select-change` in the raw data,
because native headless Chrome dropdown interaction was unreliable. Project,
filter, history, and pagination controls use CDP mouse input. Timings start
outside the renderer at input dispatch and end after matching content plus a
render opportunity; they do not measure physical monitor presentation.

The first round starts with an empty disk cache. Its worst times were Linux
653 ms, LLVM 812 ms, Kubernetes 352 ms, CPython 165 ms, Rust 350 ms, and Git
175 ms. These misses remain in [browser.json](browser.json), alongside all later
samples. No slow samples were discarded. There were no browser console errors.

The browser run contains 162 main interaction samples (three rounds × six
repositories × nine actions), plus five pagination/refresh setup actions.
Another 480 authenticated HTTP samples cover four routes, both checkouts, and
ten repetitions. Their maximum was 206.18 ms. These HTTP samples run after the
browser exercise, so they are not independent cold-start results.

After creating and staging a new file with the view already open, it appeared
without manual refresh after **47.374 seconds**. The normal timer and cache TTL
were used; timestamps were not modified for this check.

LLVM's initial 24-hour time filter still required an **8.402-second** background
scan. It rendered 200 rows, and loading the next 200 took **410 ms**. The time
filter is a separate limitation from the prioritized Git comparisons.

## Changes

Project and worktree scopes request only the immediate directory children.
Opening a folder loads its children on demand. Existing folder nodes survive
refreshes, retaining expansion and scroll state. Workspace Root continues to
use its existing workspace sections and snapshot path.

SQLite snapshots live under the authenticated vault at
`.lab/cache/sidebar-v1.sqlite3`. A cached response is immediately usable for
60 seconds and remains visible while a background job refreshes stale data.
Snapshots survive server restarts. Failure preserves the previous good result.
The browser uses the server snapshot age, so revisiting a view does not extend
its freshness window by another minute.

Opening a project warms its Uncommitted, recent-history, and local-main
snapshots. Only requested projects and expanded folders refresh; there is no
periodic sweep of every project in every workspace. Visible views check for
expiry every five seconds without doing Git work until their snapshot is due.
Background refresh stops when the document is hidden and resumes on return.

Small diffs check Git tracking/ignore membership only for their candidate paths.
A fresh Uncommitted snapshot can narrow the local-main comparison, but Git still
compares the final working tree against the base. This includes staged and
unstaged edits and correctly omits a branch edit reverted locally to the base.
Large candidate sets use the full comparison. Untracked and ignored files keep
the existing exclusion from Recently updated.

Recent file lists are sorted and filtered on the server, with 200 entries per
page. SQLite JSONB is used where supported, with a JSON-text fallback for older
SQLite versions. The browser does not decode the whole LLVM file list to display
the first page. Recent history starts with 20 commits in the last 60 days;
older pages keep the existing pinned-revision behavior.

## Resource limits and observations

- Two background Git workers, serial execution per checkout, and one separate
  shallow-directory worker prevent a slow Git scan from blocking folder reads.
  Each store admits at most 32 jobs.
- Per-vault retention is capped at 256 snapshots and 128 MiB of payloads, with a
  64 MiB single-snapshot limit. SQLite reuses freed pages; database allocation
  and transient journal space can exceed the retained-payload limit.
- Normal responses are persisted instead of retained in a Python payload map.
  Disk failure has a bounded 2 MiB in-memory fallback per store. Building a large
  time snapshot still requires temporary Python allocations; this is not a
  total process RSS limit.
- The browser response cache retains at most 64 entries and an estimated 2 MiB
  of serialized UTF-16 data. Object overhead and mounted DOM are additional.
  The existing DOM scope cache retains at most eight scopes.
- The final database occupied **34,496,512 bytes**. Git, history, status and
  directory payloads occupied **337,000 bytes**; two time-filter snapshots
  accounted for **34,078,297 bytes** of payloads.
- Chrome reported 5,446,440 bytes of JavaScript heap after the main rounds and
  4,819,340 bytes after the large time list. These are point-in-time heap
  observations, not peak memory or whole-browser RSS measurements.

## Verification and reproduction

The affected Python/Node regression checks passed **151 tests** (149 in the
combined run, plus two navigation checks added during final review; affected
navigation tests were rerun). Coverage
includes disk persistence, failure recovery, bounded eviction and scheduling,
vault isolation and path authorization, literal Git paths, staged/unstaged
comparisons, reverted branch changes, page filtering, history, and navigation
ownership. JavaScript syntax and `git diff --check` also passed.

Use disposable clones only: the harness creates fixture commits, changes their
local `main` reference, stages files, and creates linked worktrees. It creates
its isolated vault and workspace through `lab`, and uses an ephemeral server
port and a private Chrome profile. It requires the installed core environment,
Node with built-in WebSocket support, and macOS Google Chrome.

```sh
fixture_root=$(mktemp -d /tmp/lab-sidebar-benchmark.XXXXXX)
for upstream in torvalds/linux llvm/llvm-project kubernetes/kubernetes python/cpython rust-lang/rust git/git; do
  git clone --depth=25 "https://github.com/$upstream.git" "$fixture_root/${upstream##*/}"
done
core/.venv/bin/python scripts/perf/large_project_sidebar.py \
  --root "$fixture_root" --output /tmp/sidebar-results.json --browser --clear-cache
```

The normal workspace UI can create a terminal in the disposable workspace.
Clean up only that exact fixture-owned terminal, then remove the disposable
fixture directory after saving results. Never use personal checkouts or a
shared vault as `--root`.

Evidence: [browser samples](browser.json), [HTTP samples and revisions](http.json),
and [rendered sidebar](sidebar.png). Harnesses:
[`large_project_sidebar.py`](../../../scripts/perf/large_project_sidebar.py) and
[`large_project_sidebar.mjs`](../../../scripts/perf/large_project_sidebar.mjs).
