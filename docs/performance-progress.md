# UI response budget work

The target remains **every interaction and backend response below 200 ms**,
with terminal typing below 50 ms and a defensible comparison with iTerm2.
The work is incomplete. Passing a warm-path percentile does not establish
that every action, cold request, or keystroke meets the budget.

## September 22, 2026 checkpoints

- `a9f0314`: restrict agent process discovery to requested TTYs. The Mac's
  whole-process `ps` took 185–196 ms in three samples; a two-TTY selection
  took 4.5–5 ms. Preserve PID/TTY membership checks and metadata behavior.
- `b63197a`: resolve unknown terminal UUIDs once per vault. The same Home
  listing previously made 108 ownership lookups and 540 pseudo-workspace
  metadata resolutions. Profiled reconciliation fell from about 70 ms to
  3–6 ms. Index precedence, durable recovery, renamed folders, pseudo
  scopes, foreign-session exclusion, and fresh external edits are covered.

No metadata fields, transcript lookup, saved ordering, completion detection,
legacy session discovery, or authorization checks were removed. Provider
SQLite databases remain read-only. Existing metadata TTLs are unchanged.

## Measurements

The baseline used the running local server and its real vaults. Candidate
HTTP measurements used an isolated loopback Uvicorn instance with the same
vault data, production routes and auth middleware, and a materialized index.
The candidate did not start duplicate watchers, supervisors, notebook
kernels, or terminal processes. Background activity therefore differs; these
are diagnostic observations, not a controlled proof of production latency.
The live server was not restarted for these measurements.

| Request | Live baseline maximum (20 samples) | Candidate first request | Candidate maximum (30 samples) |
| --- | ---: | ---: | ---: |
| `/` | 11.00 ms | 48.34 ms | 48.34 ms |
| `/api/ping` | 3.43 ms | 0.83 ms | 2.41 ms |
| `/api/vaults/workspaces` | 19.96 ms | 3.50 ms | 7.29 ms |
| `/api/term/sessions` | 89.68 ms | 26.02 ms | 45.95 ms |
| `/api/term/sessions?workspace_id=__self__` | **226.88 ms** | **529.63 ms** | **529.63 ms** |

The candidate Home request had median 11.35 ms and p95 121.12 ms, but the
first request still failed. Earlier live probing also observed a 610 ms
Home request. Further profiling identifies provider SQLite log grouping
and snapshot discovery as remaining cold-path work. One read-only probe
measured snapshot lookup at 122.64 ms alone. Do not hide that miss behind a
warm-up phase or raise the budget.

Terminal observations on the live server, using a newly created disposable
raw-echo terminal (never typing into a user's session):

- 100 transport samples, quiet: p50 0.79 ms, p95 1.33 ms, maximum 9.44 ms.
- 100 transport samples, metadata polling: p50 0.75 ms, p95 1.05 ms,
  maximum 2.24 ms.
- 100 synthetic keyboard-to-xterm-render samples: p50 1.90 ms,
  p95 19.30 ms, maximum 24.80 ms; WebGL enabled, no observed long tasks.
- Empty-page browser control: frame intervals p95/max about 16.8 ms.

These browser numbers exclude keyboard hardware and display scanout, and
cover one terminal surface/workload. They do not prove equal latency to
physical typing in iTerm2. The [iTerm2 rendering documentation](https://iterm2.com/documentation-preferences-general.html)
describes throughput/frame-rate tradeoffs and potential 120 FPS operation;
it does not promise a fixed keyboard-to-screen latency. An 8.3 ms frame
period at 120 FPS is not an end-to-end input latency measurement.

## Verification and remaining work

The targeted terminal, workspace-rename, cross-vault, WebSocket, completion,
and existing latency tests passed: **196 tests**. The complete CLI suite
passed: **274 tests**. The broad backend/frontend run finished with **1,087
passed, 2 failed, 11 deselected**. Both failures reproduce on unchanged main
(`90fe436`): the Assistant attributes browser fixture times out waiting for its
mock save, and the Markdown clipboard fixture searches for a removed
`addCopyButtons` function. They are not caused by these backend changes;
the broad suite is not fully green. Functional fixtures use temporary vaults and dedicated
tmux sockets; notebook/real-tmux checks require local socket access.

Still required before claiming the original goal is achieved:

- Remove and remeasure the cold Home/agent-metadata overrun, including
  large provider histories and mixed agent sessions.
- Measure actual browser clicks through a visible updated frame for cold
  and warm workspace, terminal, document and Assistant navigation; cover
  rapid switching and retained user state.
- Inventory the remaining UI actions and their backend requests, including
  creation, editing, saving, search, menus, settings, server and notebook
  controls. Optimize remaining over-budget paths without removing behavior.
- Verify typing under concurrent output, polling, many tabs, cold attaches,
  reconnects and document terminal use. Obtain a comparable local iTerm2
  baseline; a frame-rate calculation is insufficient.
- Verify the integrated candidate under the normal production lifecycle,
  with background workloads, and preserve every observed over-budget sample.

Repeatable probes from the checkout:

```sh
core/.venv/bin/python scripts/perf/lab_http_latency.py --samples 30 --interval .3
core/.venv/bin/python scripts/perf/lab_terminal_latency.py --samples 200
core/.venv/bin/python scripts/perf/lab_terminal_latency.py --browser --samples 200
```

The HTTP probe accepts additional absolute request paths and an optional
`--base-url` for an isolated loopback candidate server. It includes the first
sample, raises on HTTP errors, performs no retries, prints every over-budget
sample, and exits nonzero if any request reaches 200 ms. Its default route
list is deliberately limited and is not a comprehensive UI performance gate.

## Follow-on: snapshot query, isolated on `perf/cold-metadata`

This branch builds on the three checkpoints above; `perf/response-budget`
remains unchanged while its local merge approval is pending. No merge or push
has occurred. Automatic approval review rejected merging into `main`; an
explicit approval question is pending rather than bypassing that restriction.

The next change avoids loading log records for named threads whose snapshot
is already covered by their first-pass maximum timestamp. It uses existing,
read-only provider indexes only when their columns match and the recent window
exceeds 1,024 entries. Small windows and older schemas retain the previous
query. Untitled and unprojected conversations remain eligible. Nanosecond and
row-ID ordering are explicit to preserve the timestamp index's tie behavior.

Validation includes 24 randomized equivalence cases with multiple native
processes per TTY, reused PID generations, unknown threads, missing names,
archived/API threads, and tied seconds, plus explicit nanosecond ordering,
`/new`/`/clear`, and old-schema fallback cases. **160 targeted terminal,
activity, metadata and latency tests passed** after the final query changes.

Observed evidence, with all misses retained:

- A deterministic 20,000-row fixture with 8 KiB payloads reduced the snapshot
  query from 4.27–4.65 ms to 0.82–0.86 ms in six alternating runs. This measures
  only that query, not the earlier process/thread grouping or full endpoint.
- A live alternating comparison before the small-window guard returned
  identical mappings in 24 pairs. Baseline median/p95/max: 35.80/36.92/113.89 ms;
  candidate: 36.21/37.29/38.27 ms. Warm latency was effectively unchanged, and
  OS-cache effects prevent treating those maxima as a controlled cold comparison.
- The final adaptive query also returned identical mappings in 24 live pairs.
  Baseline median/p95/max: 36.03/38.89/87.90 ms; candidate:
  36.47/39.22/40.87 ms. Neither version exceeded 200 ms in this warm-OS-cache
  comparison, which does not negate the HTTP cold-request failures below.
- An initial 30-request HTTP run had Home maximum 154.77 ms. Five fresh-process
  runs then had first Home requests 153.74, 70.51, 71.91, 70.88 and 71.69 ms.
  One global terminal-list request in those runs still took **1,086.88 ms**.
- The final adaptive candidate's 30-request run **failed**: Home first/max
  **418.44 ms**, another Home request **241.90 ms**, and the global terminal
  list first/max **1,093.33 ms**. These results supersede any impression that
  the initial passing Home runs proved the cold path solved.
- Profiling the global request reproduced **1,089.54 ms**, with **1,063 ms**
  spent reading runtime metadata in `_load_meta`. Its next request took
  49.20 ms. This identifies another storage-sensitive first-request path;
  it is not attributed to browser rendering or hidden behind a warm-up.

The original 200 ms objective remains unachieved. Further work must address
cold runtime metadata reads and provider process/thread grouping, as well as
the browser-action and typing coverage listed above. The new comparison tool
can be run with:

```sh
core/.venv/bin/python scripts/perf/lab_codex_metadata_latency.py \
  --baseline perf/response-budget --samples 24
```

It alternates invocation order, clears the metadata TTL before every call,
checks full result equality without printing private content, and reports
all candidate samples at or above 200 ms as failures. It does not flush the
OS file cache or change provider data.

## Follow-on: early workspace clicks

The browser probe found an explicit 750 ms startup timer on user navigation.
`selectRepo` inferred cold startup from page age, so clicking an already visible
workspace tab during the first two seconds postponed both dashboard/sidebar
hydration and terminal restoration. Only initial URL dispatch now opts into
that scheduling. Tab clicks, workspace opening, and back/forward navigation
start hydration immediately. Remembered documents and terminal scope guards
remain in place. Full-page startup itself is still deferred and requires work.

The new `scripts/perf/lab_navigation_latency.py` runs a normal-lifespan local
server with polling enabled, two CLI-created temporary workspaces, two Markdown
documents per workspace, and a fresh headless Chrome profile. All registry,
auth, Assistant and framework paths belong to the disposable fixture. Automatic
agent creation is disabled using the fixture's real UI preference endpoint;
there are no live terminals in this workload. The running user server and
saved user tabs are untouched.

The first tab click runs as soon as tabs appear. The probe uses real CDP mouse
input and waits for complete dashboard/document content followed by an animation
frame and task. This estimates a browser paint opportunity, not physical display
scanout. It retains every sample and API timing, includes background requests,
reports HTTP/network/browser errors, and fails for any measured 200 ms miss.

| 20 samples per action | Prior JS (`01dab6e`) first / p95 / max | Candidate first / p95 / max |
| --- | ---: | ---: |
| Workspace tab → complete dashboard | **820.40 / 221.60 / 820.40 ms** | 65.60 / 72.80 / 75.00 ms |
| Sidebar document → rendered Markdown | 68.40 / 39.80 / 68.40 ms | 64.50 / 46.90 / 64.50 ms |

The baseline also recorded one `/api/workspace-info` HTTP 404; no browser
exceptions were observed. The candidate recorded **408 API requests**, maximum
**49.40 ms**, with no HTTP, network, or browser errors. Earlier diagnostic runs
reproduced the early-click reduction (799.40 → 66.10 ms); warm tab switches
were already below 78 ms. These are small-fixture results, not a replacement
for the unresolved cold real-vault metadata failures or heavy-workspace tests.

Regression coverage exercises selection while the page is only 500 ms old,
remembered documents, explicit initial-load scheduling, and stale terminal
restoration after another workspace becomes active. Existing notebook,
workspace order, navigation, picker, rename, proxy, and browser terminal
**disposal checks passed: 35 tests**. The notebook source-extraction fixture now
accepts the added optional argument to `selectRepo`.

```sh
core/.venv/bin/python scripts/perf/lab_navigation_latency.py --samples 20
core/.venv/bin/python scripts/perf/lab_navigation_latency.py \
  --samples 20 --app-revision 01dab6e
```

The earlier one-second runtime-metadata read did not recur in a follow-up
per-file probe: all three metadata files read in under 1 ms. That observation
does not resolve or invalidate the previously measured storage-sensitive miss.

## Follow-on: large workspace sidebars

The browser fixture now accepts `--extra-files 2000`, adding 2,000 Markdown
notes to **each** workspace while retaining the original two documents and all
normal polling. A profile of an eight-switch run found about 1.9 seconds in
`_refreshWorkspaceSidebar`; HTML parsing and forced layout dominated. The
baseline's slowest file-list request was only 63.30 ms. This is a browser
rendering problem as well as a backend budget exercise.

Changes in this checkpoint:

- Keep reading the saved workspace flag, but do not rewrite it when the tab
  is already open. The old no-op PUT changed workspace.json's mtime and caused
  additional file-tree reconciliation and DOM replacement. An external close
  is still detected and reopened, with other metadata preserved.
- Reuse one natural-sort `Intl.Collator` with the existing numeric/base options.
- Cache parsed sidebar templates by exact markup and workspace scope. Stable
  folder IDs make identical trees reusable. Mount fresh clones so previous
  selection, Git badges, controls, or listeners cannot contaminate a revisit.
  Retention is capped at four scopes and 60,000 aggregate elements. Oversized
  trees remain fully rendered but are not retained in the cache.
- Extend the probe with large fixtures, optional Chrome CPU profiling, settled
  scroll coordinates before clicking, and partial result reporting on failure.

No file rows, actions, metadata, refreshes, or sorting choices are removed.
The dashboard still waits for its existing sidebar refresh path. Concurrent
fetching was tested and reverted after it worsened cold samples; row-level
rendering containment was also reverted after it failed click targeting.

| 20 samples per action, 2,000 extra files per workspace | Before median / p95 / max | Final candidate median / p95 / max |
| --- | ---: | ---: |
| Workspace switch | **290.20 / 390.90 / 393.80 ms** | 166.90 / **238.40 / 252.70 ms** |
| Document click | 33.90 / 54.40 / 199.70 ms | 29.00 / 50.80 / 61.40 ms |

The final large run **still fails**: its two cold workspace visits took
**238.40 ms and 252.70 ms**. All 18 subsequent workspace switches were below
186.80 ms. The baseline first click was 234.50 ms, so cold performance has not
been demonstrated to improve. All 337 recorded API requests stayed below
80.90 ms, with no HTTP, network, or browser errors. These fixture API results
do not erase the earlier cold real-vault metadata failures.

The small-fixture follow-up passed all 40 actions: workspace maximum 68.90 ms,
document maximum 67.20 ms, and no request/browser errors. **54 targeted tests
passed**, including real Chrome verification of cloned click handlers, clean
selection and form state, changed file lists, LRU eviction, aggregate element
limits, complete oversized trees, and existing sidebar/navigation/notebook
regressions. The probe's first two cold samples remain included in every
budget decision; the warm subset is reported only to locate remaining work.

```sh
core/.venv/bin/python scripts/perf/lab_navigation_latency.py \
  --samples 20 --extra-files 2000
LAB_PERF_CPU_PROFILE=/tmp/lab-navigation.cpuprofile \
  core/.venv/bin/python scripts/perf/lab_navigation_latency.py \
  --samples 8 --extra-files 2000
```

Use unprofiled runs for final timings. Remaining work includes cold large-tree
rendering, larger or mixed trees, rapid scope switching and state retention,
full-page startup, real-vault backend outliers, and typing under active UI and
terminal workloads. This checkpoint remains isolated; the earlier merge
approval request is still pending.

## Follow-on: cold file scans, shared icons, and sidebar races

The file-list route now uses `os.scandir` entries for type checks and stat data.
Each entry is reused only within that request. Every later request scans again,
so file changes, repaired or retargeted symlinks, notebook pending state, and
worktree checkout annotations remain live. Sorted traversal and depth limits
are unchanged. The new comparison script alternates the old and new route
implementations over a CLI-created disposable vault and checks complete response
equality on every pair. It measures filesystem route work, excluding HTTP,
authentication, and serialization, and does not flush the OS cache.

| 2,000-file scan, 20 samples per implementation | First | Median | Maximum |
| --- | ---: | ---: | ---: |
| Baseline (`7eda46a`) | 40.13 ms | 28.70 ms | 40.13 ms |
| Candidate | 18.68 ms | 18.61 ms | 20.92 ms |

The remaining browser cost includes thousands of repeated inline SVG elements.
Markdown file icons and GitHub history icons now reuse their original graphics
through CSS, reducing markup parsing and live DOM size. History buttons, click
handlers, colors, icon dimensions, and symlink overlays are preserved. A browser
comparison of the old and new icons exposed an inline-flex baseline difference;
the final CSS retains the original baseline. The final comparison was visually
checked at 3× scale. Template retention limits remain unchanged.

Sidebar refreshes now capture the workspace path, selected file root, and a
generation number. Delayed file or metadata responses cannot paint or populate
the cache after a newer refresh or scope change. Cached paint and its background
reconciliation share the same generation. Nine controlled async tests cover
delays during worktree discovery, file fetches, and metadata fetches while the
workspace, worktree, or refresh changes. Existing sidebar and backend coverage,
including fresh edits and symlink retargeting, passed: **124 targeted tests**.

The final unprofiled 40-action run used 2,000 extra Markdown files per workspace:

| Action, 20 samples each | First | Median | p95 | Maximum |
| --- | ---: | ---: | ---: | ---: |
| Workspace tab → complete dashboard | 175.20 ms | 102.00 ms | 163.50 ms | 175.20 ms |
| Sidebar document → rendered Markdown | 60.30 ms | 30.40 ms | 45.10 ms | 60.30 ms |

All **335 API requests** stayed below **66.00 ms**, with no HTTP, network, or
browser errors. Five additional fresh-server/fresh-browser runs each included
both cold workspace visits. Their workspace maxima were **184.50, 198.60,
179.40, 179.60, and 183.10 ms**. All ten document clicks stayed below 66.20 ms.
The 198.60 ms sample leaves little margin; these runs establish only the measured
fixture result, not a general cold-start guarantee.

Broader fixtures **still fail** and remain part of the performance record:

- With 2,000 extra files rotated through Markdown, Python, JSON, and SQL, the
  first workspace visit took **230.50 ms**. The other nine workspace visits
  passed; document maximum was 51.90 ms and API maximum 75.00 ms.
- With 5,000 extra Markdown files, all four workspace visits missed: **377.10,
  400.30, 264.90, and 248.60 ms**. Document maximum was 58.70 ms and API maximum
  125.90 ms. There were no request or browser errors in either broader run.
- Before sharing icons, the scan/race candidate still reached 227.00 ms;
  sharing only the GitHub icon reached 212.60 ms. Those misses are not excluded
  from the investigation because the final Markdown fixture passed.

Reproduce the scope and response-equality checks with:

```sh
core/.venv/bin/python scripts/perf/lab_file_scan_latency.py --samples 20
core/.venv/bin/python scripts/perf/lab_navigation_latency.py \
  --samples 20 --extra-files 2000
core/.venv/bin/python scripts/perf/lab_navigation_latency.py \
  --samples 10 --extra-files 2000 --extra-file-types md,py,json,sql
core/.venv/bin/python scripts/perf/lab_navigation_latency.py \
  --samples 4 --extra-files 5000
```

The overall goal remains unfinished: larger and mixed sidebar rendering,
full-page startup, the earlier cold real-vault metadata outliers, additional UI
actions, and typing under active UI/terminal workloads still require work. This
checkpoint is on `perf/cold-metadata`; main and the live server are unchanged.
