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

## Follow-on: file-list response serialization

The file-list route now declares `list[dict[str, Any]]` as its response model.
The generic dictionaries retain every metadata key and value while selecting
FastAPI/Pydantic's compiled serialization path, avoiding an additional Python
walk of the large result. This follows the
[FastAPI response-model guidance](https://fastapi.tiangolo.com/tutorial/response-model/).
The installed comparison used FastAPI 0.139.2 and Pydantic 2.13.4; no dependencies
were changed. Filesystem discovery and access checks remain unchanged.

The file-scan comparison tool now supports `--transport asgi`, which registers
both implementations with their respective response models in a minimal
TestClient app. It includes worker dispatch, response validation, serialization,
and client JSON decoding. It excludes sockets and production middleware; a
fixture-only adapter supplies the same user state to both routes. Twenty
alternating pairs over 5,000 files, including valid and broken links, produced
identical complete JSON results:

| ASGI request | First | Median | Maximum |
| --- | ---: | ---: | ---: |
| Untyped response (`cc9e13b`) | 80.70 ms | 73.99 ms | 80.70 ms |
| Typed generic dictionaries | 52.44 ms | 53.21 ms | 58.72 ms |

In the normal-server 5,000-file browser fixture, the four large file-list HTTP
requests took **95.80, 79.80, 75.90, and 71.90 ms**. Workspace navigation still
failed at **367.30, 369.40, 269.10, and 243.70 ms**; document maximum was
62.50 ms. Rendering remains substantial even after the serialization reduction.

The mixed 2,000-file fixture's 40-action run passed: workspace first/max
**197.30 ms**, median 148.40 ms, p95 179.70 ms; document maximum 64.80 ms.
All **338 API requests** stayed below **60.70 ms**, with no request or browser
errors. However, five further fresh-browser runs found two misses: their cold
workspace maxima were **200.30, 195.40, 195.40, 199.70, and 201.00 ms**.
Document clicks stayed below 66.50 ms and APIs below 48.00 ms. The mixed-tree
budget therefore remains **unresolved**, despite the passing 40-action run.

The browser probe now observes clicks at document capture phase and reacquires
the target after scroll/layout settles. A normal background sidebar reconcile
can replace the earlier row and its attached probe listener. Unexpected actual
click targets fail explicitly; timeout reports include whether the planned
coordinates hit the intended row. The probe still sends real CDP mouse input
and requires complete content plus a frame/task paint opportunity.

A new trial of row-level `content-visibility` completed clicks with this probe:
5,000-file warm switches reached 168.00 and 164.90 ms, but cold visits still took
333.30 and 328.00 ms. The CSS experiment was **reverted**; it is not part of the
checkpoint and has not received full interaction/visual regression coverage.
The earlier targeting failure is no longer sufficient evidence of a product
bug, but neither does this small trial establish that containment is safe to ship.

All **56 backend/worktree/Assistant regression tests** passed after the response
model change, covering file dates, links, pending notebooks, and depth behavior.
The earlier checkpoint's 124-test result remains recorded separately.

```sh
core/.venv/bin/python scripts/perf/lab_file_scan_latency.py \
  --baseline cc9e13b --files 5000 --samples 20 --transport asgi
core/.venv/bin/python scripts/perf/lab_navigation_latency.py \
  --samples 20 --extra-files 2000 --extra-file-types md,py,json,sql
```

This checkpoint also remains isolated on `perf/cold-metadata`. The overall goal,
including the earlier real-vault outliers and broader action/typing coverage,
is still active.

## Follow-on: complete large trees with less rendering work

This checkpoint retains every file row while reducing cold parsing, layout, and
filesystem work. The existing four-scope/60,000-element template limit stays in
place; no larger cache is used to make the fixture pass.

- Recently updated folders use `content-visibility: auto` with an initial
  extent derived from visible row counts and the existing 22px row metric.
  Flat folders above 200 files also use plain, unindented groups of 100 rows.
  All rows remain in the DOM, including native find-in-page and action metadata.
- Workspace, framework, vault, and recent-file rows share file/history handlers
  on the sidebar. Paths and roots come from escaped row attributes, preserving
  double-click modals and stopping history/control clicks from opening files.
- Dashboard reads start after sidebar data arrives and before HTML rendering,
  overlapping network work with parsing without placing dashboard requests ahead
  of the file scan. Request generations also guard stale success and error paths.
- Python and SQL icons reuse the original SVG graphics through CSS, as Markdown
  already did. Dark/light-background comparisons at 2× zoom confirmed the same
  shapes, text baselines, and symlink overlays. Git decorations skip unchanged
  class writes; browser mutation checks cover transitions and retained selection.
- File scans construct full `Path` objects only for links, notebook activity,
  directories, and worktree comparisons. Ordinary relative names reuse their
  parent's prefix. Change polling now uses `DirEntry` type/stat data as well.
  Both scans remain fresh per request and keep existing traversal rules.

Twenty alternating in-process ASGI pairs against `6b83eb0`, with 5,000 files,
produced identical full JSON responses in both comparisons:

| Request | Baseline median / max | Candidate median / max |
| --- | ---: | ---: |
| File list | 56.17 / 63.05 ms | 19.26 / 23.30 ms |
| Change poll (`mtime`) | 21.85 / 25.40 ms | 8.43 / 10.78 ms |

The final 40-action browser run used **5,000 mixed Markdown/Python/JSON/SQL files
in one flat folder per workspace**, normal server startup and polling, and a
fresh Chrome profile:

| Action, 20 samples each | First | Median | p95 | Maximum |
| --- | ---: | ---: | ---: | ---: |
| Workspace tab → complete dashboard | 171.80 ms | 115.70 ms | 154.60 ms | 171.80 ms |
| Sidebar document → complete content | 57.50 ms | 31.10 ms | 50.00 ms | 57.50 ms |

All **333 API requests** stayed below **50.20 ms** with no HTTP, network, or
browser errors. Four further fresh-browser runs passed with workspace maxima
**163.30, 167.00, 161.60, and 166.10 ms**, document maximum 62.30 ms, and API
maximum 50.00 ms. A fifth attempted run failed with `fetch failed` before any
action or request timing was collected; it is incomplete evidence, not a pass.
The probe now lets Chrome reserve an ephemeral DevTools port instead of selecting
a random port from a fixed range, and includes exception cause/stack in failures.
The specific cause of that prior connection failure was not established.
The subsequent ephemeral-port run connected successfully but found a **214.60 ms
cold workspace open** (document maximum 60.40 ms; 50 APIs, maximum 89.30 ms).
Thus the final candidate still has a verified cold UI miss. Neither the passing
40-action run nor the four passing repeats proves the cold budget solved.

Earlier combined Markdown runs passed with grouped-folder
workspace maximum 167.60 ms and flat-folder maximum 165.40 ms; the flat Markdown
run recorded 336 APIs, maximum 103.90 ms.

The investigation also found failures that remain part of the record:

- Grouped rendering alone reached 264.50 ms; sharing file handlers reduced
  the tested cold maximum to 227.80 ms, and overlapping dashboard reads reached
  211.30 ms. These were intermediate candidates, not passing checkpoints.
- Before plain file groups were added, a flat 5,000-file Markdown folder reached
  267.00 ms, and all four workspace samples missed the budget.
- Before the polling change, a mixed-file run passed UI timings at 181.40 ms
  maximum but failed a background `/api/workspace-mtime` request at **228.30 ms**.
- Before shared Python/SQL graphics, later mixed-file cold opens still reached
  **200.70 ms and 250.50 ms**. Five fresh-browser maxima were 207.80, 202.40,
  184.20, 180.90, and 185.70 ms. These misses are not discarded because a later
  candidate passed.

Validation: **122 targeted tests passed** across sidebar, navigation, dashboard,
notebook, file, worktree, and Assistant routes. After the final polling change,
42 workspace tests passed; after the final graphics/mutation changes, 23
sidebar/dashboard tests passed. The two real-Chrome rendering cases cover nested
and flat 5,000-file layouts, 220px/340px widths, 100%/125% zoom, scroll extents,
hit targets at top/middle/end, native find-in-page, folder collapse/reopen and
Cmd-click, file/history/double-click actions, quoted/Unicode paths, and preserved
drag/context metadata. Existing context-menu source checks now recognize the
delegated handlers. The side-by-side visual check also matched.

```sh
core/.venv/bin/python scripts/perf/lab_file_scan_latency.py \
  --baseline 6b83eb0 --files 5000 --samples 20 --transport asgi
core/.venv/bin/python scripts/perf/lab_file_scan_latency.py \
  --baseline 6b83eb0 --files 5000 --samples 20 --transport asgi --endpoint mtime
core/.venv/bin/python scripts/perf/lab_navigation_latency.py \
  --samples 20 --extra-files 5000 --extra-file-layout flat \
  --extra-file-types md,py,json,sql
```

The overall objective remains active. These fixtures do not resolve earlier
real-vault cold metadata outliers, full-page startup, all remaining UI actions,
or typing latency during active UI/terminal workloads. No merge or live-server
restart is included in this checkpoint.

## Follow-on: queued terminal input and unchanged sidebar refreshes

The earlier synthetic typing probe started its clock inside the browser and used
`ui_check=1`, which disables normal polling. It could not see keys waiting behind
a busy main thread. The navigation fixture now supports `--typing`: it creates
one owned raw-echo terminal in its disposable workspace, uses normal UI polling,
and sends native CDP keys from Node with explicit timestamps. The timestamps are
checked against the resulting browser events. Keys are posted without waiting
for renderer acknowledgments, so a blocked browser cannot silently delay the
start of a sample. This follows the timestamp field in Chromium's
[input protocol](https://chromium.googlesource.com/devtools/devtools-frontend/+/main/third_party/blink/public/devtools_protocol/browser_protocol.json).

Every character must appear in xterm's buffer in order and receive a render
callback covering the echo cursor. Wrapped lines remain part of the check;
tmux's separate status bar is excluded by reading through the app cursor.
The result retains all keys, pre-handler queue time, parse/render timestamps,
browser/API failures, and an empty-page frame control. Neither hardware input
nor physical display scanout is measured. The second phase deliberately refreshes
the sidebar every 500 ms; this is controlled load, not a claim about production
refresh frequency. The fixture removes only its own terminal afterward.
Navigation clicks now also start from the externally timestamped mouse release.

The new baseline found 14 keys at or above 50 ms in a 200-key run. CPU profiling
showed repeated sidebar replacement as a substantial cost. Background refreshes
now retain live rows when newly generated markup, scope, and mounted root identity
are unchanged. They still read fresh data and compute current selection, folder,
filter, and notebook state. Explicit navigation, changed markup, and a replaced
view still rebuild. Instruction-file and Git refreshes continue. Template cache
bounds are unchanged.

Unprofiled measurements, 5,000 mixed Markdown/Python/JSON/SQL files in one folder,
100 keys per phase, including first input:

| Phase | Baseline median / p95 / max | Candidate median / p95 / max |
| --- | --- | --- |
| Normal polling | 3.90 / 32.50 / 128.40 ms | 3.50 / 23.10 / 117.10 ms |
| Controlled sidebar refreshes | 9.00 / 74.40 / 102.40 ms | 3.50 / 41.40 / 66.60 ms |

The candidate still failed the typing target: **3 normal-polling keys and 5 keys
under refresh load** reached 50 ms. All 200 characters arrived correctly, no input
timestamp mismatch or skipped render range occurred, and all 57 API requests
stayed below 56.10 ms. The empty-page frame maximum was 16.80 ms. Source posting
slip was at most 2.85 ms and is reported separately. These measurements are from
`/tmp/lab-typing-baseline.json` and `/tmp/lab-typing-final.json`.

A Chrome timeline found a separate 94.52 ms layout task during normal typing.
An invalidation trace identified `DisplayLock` changes for the offscreen sidebar
groups immediately before a 153.96 ms layout in that instrumented run. There was
no Lab sidebar replacement at that point. The underlying browser trigger remains
unresolved; this evidence does not justify disabling browser features or hiding
files. Unchanged-render CPU work also remains: final controlled refreshes took
39.90–55.50 ms. Profiling numbers are diagnostic, not final latency claims.

A small-workspace repeat passed with normal/loaded typing maxima **34.20 / 29.70
ms**, 57 API requests below 37.20 ms, and no lost input. An earlier small-workspace
run had an unexplained **581.70 ms** render completion affecting its final 18 keys,
without a long main-thread task. The repeat does not erase that failure. Parse
timestamps and skipped-render diagnostics were added afterward to distinguish
transport/parse delays from render-range issues if it recurs.

Validation: **33 tests passed** across sidebar cache/state, stale navigation,
5,000-file Chrome rendering and interactions, file configuration, and dashboard
loading. The added checks cover retaining rows/focus/Git state on unchanged
background refreshes, rebuilding changed files, pristine explicit navigation,
scope changes, and invalidation after another view replaces the sidebar. JS
syntax, Python parsing, and whitespace checks passed.

Final timestamped navigation validation passed all 40 actions: workspace first
and maximum **167.80 ms**, median 113.20 ms; document maximum **66.50 ms**, median
34.20 ms. All 335 APIs stayed below 70.10 ms, with no HTTP, network, browser, or
timestamp errors. Maximum measured click queueing was 1.60 ms. Earlier cold
navigation failures remain unresolved rather than being superseded by this run.

```sh
core/.venv/bin/python scripts/perf/lab_navigation_latency.py --typing \
  --samples 100 --extra-files 5000 --extra-file-types md,py,json,sql \
  --extra-file-layout flat
core/.venv/bin/python scripts/perf/lab_navigation_latency.py \
  --samples 20 --extra-files 5000 --extra-file-types md,py,json,sql \
  --extra-file-layout flat
```

Optional `LAB_PERF_CPU_PROFILE=/tmp/input.cpuprofile` or
`LAB_PERF_TRACE=/tmp/input-trace.json` captures browser diagnostics. The overall
goal remains active, including real-vault metadata outliers, cold startup, other
UI actions, and typing under active workloads. No main-branch merge or live-server
restart is included.

## Follow-on: remove redundant refresh passes and test changing files

Recent-folder compaction no longer sorts every leaf just to check whether it is
empty. Sorting by update time derives names only for timestamp ties, and basename
extraction avoids creating a split array. Attribute escaping returns unchanged
strings immediately when they contain no escapable characters. Quoted and Unicode
paths retain the same escaping. Unchanged sidebar rows skip another full scan to
reapply fresh cached Git styling; rebuilt rows still receive it, and stale or
missing status still fetches and applies with the existing scope guards. A Git
repaint resolves the selected root once instead of once per row.

The final unprofiled unchanged-refresh fixture, 5,000 mixed files and 100 keys per
phase, measured:

| Phase | Median | p95 | Maximum | Keys at/above 50 ms |
| --- | ---: | ---: | ---: | ---: |
| Normal polling | 3.30 ms | 31.40 ms | 117.30 ms | 3 |
| Controlled unchanged sidebar refreshes | 3.30 ms | 23.50 ms | 41.80 ms | 0 |

All 200 characters arrived, and all 57 API requests stayed below 53.60 ms without
HTTP, network, browser, or timestamp errors (`/tmp/lab-typing-fast-paths.json`).
The intermediate candidate before the string/sort changes still had a 55.70 ms
loaded maximum. This is one passing loaded phase, not proof of the entire typing
target: the startup miss remains and changing data requires separate coverage.

The trace now includes blink/display-lock events and records the browser version.
It identified **`AIPageContentAgent::ContentBuilder::Build` in Chrome
153.0.8010.53** enclosing a **138.78 ms** layout, with total extraction lasting
147.72 ms. This matches Chromium's implementation, which forces activatable
display locks before collecting page content.
[Chromium page-content extraction source](https://chromium.googlesource.com/chromium/src.git/+/e68d8f976b1e536fe6d7716affec062208e26112/third_party/blink/renderer/modules/content_extraction/ai_page_content_agent.cc)
The trace is `/tmp/lab-typing-blink-trace.json`. Browser features remain enabled.
A fixed-height row-containment experiment still produced a 93.80 ms startup key
and a 109 ms long task; it was removed rather than changing dynamic sizing for
an unproven improvement.

New `--typing-updates` coverage alternates writes to the disposable fixture's two
Markdown documents during the loaded phase. It verifies their actual mtimes in
the sidebar cache and their final rendered recent-file order. It does not write
to user documents. Five writes in a 200-key run exposed **7 loaded keys at or
above 50 ms**, with loaded median **7.70 ms**, p95 **61.90 ms**, maximum **87.30
ms**. Normal-polling maximum was 101.10 ms (2 misses). All characters, metadata,
and final ordering passed; all 96 APIs stayed below 50.90 ms with no errors
(`/tmp/lab-typing-changing-files.json`). Incremental updates for changed sidebar
sections remain necessary; unchanged-tree reuse alone is insufficient.

Final navigation kept 39 of 40 actions below 200 ms, but the **first workspace
open reached 204.40 ms**. Workspace median was 111.40 ms and p95 148.90 ms;
document maximum 69.70 ms. All 333 APIs stayed below 79.40 ms, with no browser,
HTTP, network, or timestamp errors (`/tmp/lab-navigation-redundant-passes.json`).
The mouse probe now posts press/release together without waiting for a renderer
acknowledgment between them, preserving queued input in the measurement.

Validation: **41 sidebar, configuration, dashboard, navigation-race, and real
Chrome rendering tests passed**, including new cases for retained/rebuilt rows,
fresh/stale/missing Git status, and an in-flight worktree switch. JS syntax and
whitespace checks passed. No backend behavior, browser setting, or live-server
configuration was changed. The goal remains active.

```sh
core/.venv/bin/python scripts/perf/lab_navigation_latency.py --typing \
  --typing-updates --samples 100 --extra-files 5000 \
  --extra-file-types md,py,json,sql --extra-file-layout flat
```

## Follow-on: reuse changed-tree sections within the existing cache bound

Background refreshes now compare old/new pristine templates and retain equal
live sections. Known folder, recent-file, and worktree containers reconcile their
children by stable identity. A reordered folder can retain its rows; adding,
removing, or relabeling a file changes the affected rows. Container sizes and
expanded state follow the new markup. An unexpected live child structure falls
back to a fresh clone, and explicit navigation still uses pristine clones.
The cache never receives live decorations. Where supported, state-preserving
DOM moves retain focus; the fallback restores only the same surviving element.
[Chrome's moveBefore documentation](https://developer.chrome.com/blog/movebefore-api)

The first large-fixture profiles still showed full replacements. Measured DOM
counts explained why: **60,189 elements exceeded the existing 60,000-element
template limit**, so no template was retained. This was a real limitation of the
earlier large mixed-file runs, not evidence that the new reconciliation code was
active. A history button no longer needs a nested icon span; its identical shared
mask now paints on `::before`. Removing those wrappers brought the fixture to
**55,185 elements**, with a 55,185-element pristine template actually retained.
Both cache limits remain unchanged.

The final unprofiled changing-file run retained all 200 keys and five fixture
writes, verified actual mtimes and rendered ordering, and reported:

| Phase | Median | p95 | Maximum | Keys at/above 50 ms |
| --- | ---: | ---: | ---: | ---: |
| Normal polling | 4.90 ms | 24.00 ms | 105.40 ms | 3 |
| Sidebar refreshes with changing documents | 9.80 ms | 50.20 ms | 70.70 ms | 6 |

All 107 API requests stayed below **59.70 ms**, with no HTTP, network, browser,
input-timestamp, or echo-content errors. Empty-page frame maximum was 16.80 ms
(`/tmp/lab-typing-incremental-fit.json`). The loaded maximum was 87.30 ms before
this part. Earlier incremental experiments that did not fit the cache still
reached 104.40 and 79.60 ms and are not counted as passes. The changed full
template still has to be parsed; remaining refresh tasks reached 51–65 ms.
The browser's startup extraction delay also remains.

Validation: **41 tests passed** across sidebar cache/state, configuration,
navigation races, dashboard loading, and Chrome rendering. After adding repeated
update sequences, the nine cache/Git tests passed again. The Chrome checks cover
30 successive insertion/deletion/reordering/label-change combinations against a
fresh DOM, external subtree mutation, focus on retained controls (including the
move fallback), preserved Git badges and handlers, pristine cached templates,
and cache bounds. The large rendering tests compare the original icon wrapper
against the new pseudo-element at both widths and zoom levels: button sizes and
positions, 22 px rows, file/history/modal clicks, native find, and scroll extents
matched. The side-by-side screenshot also matched visually.

Final 40-action navigation validation passed: workspace first/maximum **165.30
ms**, median 120.60 ms; document maximum **73.10 ms**, median 34.50 ms. All 336 APIs
stayed below **92.70 ms** with no HTTP, network, browser, or timestamp errors
(`/tmp/lab-navigation-incremental-final.json`). Prior cold misses remain part of
the evidence; this run does not prove the universal action budget solved.

Three additional fresh-browser runs kept workspace maxima at **163.60, 165.40,
and 165.10 ms**, with document maxima 68.20, 66.30, and 65.10 ms. The first two
recorded 53 APIs each below 42.40/42.20 ms. The third recorded a **567.20 ms
`/api/term/sessions` response** among its 53 requests, despite its passing UI
actions. It failed the overall check. No HTTP, network, or browser errors occurred;
the cause of this background request outlier has not been established. Results
are `/tmp/lab-navigation-incremental-cold-{1,2,3}.json`. This checkpoint leaves
both the typing misses and backend/request outliers open; no main merge or
live-server restart is included.

## Follow-on: distinguish request latency from server execution

The isolated navigation/typing fixture now accepts `--server-timings <json>` and
optional `--trace-sessions`. A pass-through ASGI wrapper measures response headers,
final body, and app return. Terminal-listing handler timings exclude dependency
resolution and worker-pool scheduling; optional coarse function timings cover
tmux discovery, runtime/saved metadata, vault discovery, and enrichment, including
work on fsguard threads. Browser request records now include absolute start times
and workspace scope to correlate requests. No response changes, extra warm-up
requests, user-server restart, or production instrumentation are involved.

ASGI timing starts at app entry, so it cannot identify socket acceptance or
event-loop queueing before that entry. Function durations include nested work and
must not be added together. Sidecars are written during fixture cleanup even if
the browser fails; `serverStopped` identifies incomplete shutdown. Exceptions and
responses still propagate unchanged.

An initial cProfile experiment captured unrelated server/event-loop/filesystem
thread work in its per-handler profiles on the installed Python 3.14.3. Those
profiles were not used to attribute costs. That mode was removed in favor of
direct wall timings. Its workspace click reached 202.60 ms; this diagnostic
failure is retained at `/tmp/lab-sessions-diagnostic-1-browser.json`. A subsequent
run without cProfile reached 198.90 ms, with terminal ASGI responses at 17–41 ms
(`/tmp/lab-sessions-timed-1-{browser,server}.json`).

Eight further fresh-browser runs with 5,000 mixed files per workspace, real
lifespan/polling, and direct function tracing produced:

| Run | Workspace maximum | Browser API maximum | Terminal ASGI maximum | Terminal handler maximum |
| --- | ---: | ---: | ---: | ---: |
| 1 | 215.60 ms | 55.20 ms | 23.29 ms | 15.81 ms |
| 2 | 178.50 ms | 38.70 ms | 16.04 ms | 12.92 ms |
| 3 | 184.30 ms | 41.00 ms | 16.05 ms | 12.07 ms |
| 4 | 183.20 ms | 47.00 ms | 20.81 ms | 15.71 ms |
| 5 | 169.10 ms | 36.90 ms | 16.79 ms | 12.23 ms |
| 6 | 179.40 ms | 39.70 ms | 21.91 ms | 16.24 ms |
| 7 | 179.40 ms | 38.70 ms | 19.49 ms | 14.34 ms |
| 8 | 170.60 ms | 38.70 ms | 21.66 ms | 15.66 ms |

The first run fails the UI budget. All 421 browser API requests passed, and all
server API samples were below 49.66 ms. No HTTP, network, or browser errors were
reported. Artifacts: `/tmp/lab-sessions-traced-{1..8}-{browser,server}.json`.
The previous **567.20 ms** terminal request was not reproduced. Its cause remains
unknown; these passing terminal samples do not erase it or justify a speculative
production cache/timeout change.

A 200-key live echo-terminal run with five changing-file updates retained every
key, verified final mtimes/order, and recorded no input, HTTP, network, or browser
errors. All 97 browser API requests were below **57.90 ms**; server API maximum
54.75 ms, terminal handler 21.18 ms (tmux listing 10.07 ms, enrichment 8.02 ms).
Typing still failed: normal median 3.80 / p95 29.80 / max **104.70 ms**, with three
keys at/above 50 ms; changing-file median 10.30 / p95 48.20 / max **74.30 ms**,
with five misses. Startup input queueing reached 103.20 ms and refresh tasks
reached 59–66 ms. Artifacts: `/tmp/lab-sessions-typing-{browser,server}.json`.
The owned terminal was removed; no user terminal was changed.

Validation: **five diagnostic tests passed** for streaming response fidelity,
non-HTTP pass-through, failure recording, nested FastAPI router instrumentation,
and preserving traced function results/exceptions without logging arguments.
Both modified browser probes pass Node syntax checking; `git diff --check` passes.
This is a measurement checkpoint, with the UI/typing misses and intermittent
request outlier still open. Production code remains at the previous checkpoint.

## Follow-on: parse only changed sidebar folder fragments

Workspace Files and Recently updated now record source ranges for complete folder
elements. When building the next pristine template, exact matching source ranges
reuse clones of the previous parsed folders. The largest unchanged ancestor wins;
if an ancestor changed, unchanged descendants can still be reused. Only changed
markup and temporary placeholders enter the HTML parser. After assembly, the
template matches a full parse and contains no placeholders. Literal content using
the placeholder attribute bypasses reuse. No asynchronous rendering boundary or
new navigation race is introduced.

Fragment indexes retain offsets and nodes inside the existing template, without
an additional set of DOM copies or overlapping cached fragment strings. Existing
four-scope/60,000-element retention limits remain. A temporary clone/source map
avoids traversing known-equal cloned subtrees during live reconciliation; it is
discarded after that synchronous update, so it cannot retain older templates.
When live reconciliation only moves/deletes nodes, it also skips reapplying fresh
Git decorations. Newly mounted nodes still get cached styling, and stale/missing
Git data still fetches and applies normally.

Validation: **41 tests passed**, including both actual renderers' source ranges
and assembled DOM against complete HTML parses for nested and flat 5,000-file
trees, changing file names/selection, 30 repeated nested fragment updates, and
literal placeholder-like content. Checks cover focus, handlers, Git decorations,
explicit navigation, pristine cache state, unexpected live mutations, cache
bounds, configuration and response races. Native find, scrolling, 22 px rows,
file/history/modal clicks, folder toggles, drag/context metadata, and both widths
and zoom levels still pass. The generated screenshot was inspected and matched.
After adding the transient identity shortcut, all **nine cache/Git tests passed
again**. Node syntax checking and `git diff --check` also pass.

The first fragment-only typing run retained all 200 keys and five file updates,
and had no refresh tasks at/above 50 ms. Changing-file p95 was 39.40 ms and maximum
59.70 ms; startup maximum was still 108.50 ms. API maximum was 153.60 ms. Artifact:
`/tmp/lab-sidebar-fragment-browser.json` (overall typing failure retained).

A sequential prior-checkpoint/candidate comparison, followed by a flat-layout run,
used fresh Chrome profiles and normal server lifespan/polling. Each typed 100 keys
per phase while alternating five fixture-file updates in the loaded phase:

| Run / phase | Median | p95 | Maximum | Keys at/above 50 ms |
| --- | ---: | ---: | ---: | ---: |
| Prior `795241a`, normal | 3.70 ms | 22.90 ms | 97.60 ms | 2 |
| Prior `795241a`, changing files | 6.70 ms | 49.60 ms | 77.40 ms | 5 |
| Fragment + repaint changes, normal | 3.30 ms | 22.40 ms | 98.80 ms | 2 |
| Fragment + repaint changes, changing files | 11.90 ms | 44.60 ms | 55.00 ms | 3 |
| Flat layout, normal | 3.50 ms | 25.10 ms | 107.60 ms | 3 |
| Flat layout, changing files | 3.70 ms | 38.30 ms | 57.60 ms | 3 |

The prior run had 57–65 ms refresh tasks; both candidates had no refresh tasks
at/above 50 ms. Startup tasks still reached 110–116 ms. Medians vary with input
and frame timing and did not uniformly improve. All keys, updates, final mtimes,
and recent-file ordering were verified; no input, HTTP, network, or browser errors
occurred. API maxima were 51.80, 101.50, and 108.90 ms. All three runs fail the
overall typing budget. Artifacts: `/tmp/lab-sidebar-fragments-{baseline,candidate,flat}-{browser,server}.json`.

The final candidate with the identity shortcut recorded normal median 3.70 / p95
30.10 / maximum **129.50 ms** (four misses), and changing-file median 9.80 / p95
38.40 / maximum **61.40 ms** (one miss). The loaded input queue maximum was 26.80
ms, down from 45.60 ms in the prior comparison run. There were no refresh tasks
at/above 50 ms, but a 117 ms startup task remained. All 200 keys and five updates
passed content checks; 106 APIs stayed below **88.30 ms**, with no HTTP, network,
browser, or timestamp errors. The 55,435-element template remained within bounds.
The owned echo terminals were removed after every run. Artifact:
`/tmp/lab-sidebar-fragments-typing-final-{browser,server}.json`.

Final navigation passed all 40 actions: workspace first/maximum **186.30 ms**,
median 119.20 / p95 152.20 ms; document first/maximum **74.30 ms**, median 33.40 /
p95 47.60 ms. All 337 APIs stayed below **84.00 ms**, with no HTTP, network,
browser, or timestamp errors. Artifact:
`/tmp/lab-sidebar-fragments-navigation-final-{browser,server}.json`.

This checkpoint reduces changed-file refresh work. It does not establish the
50 ms typing target, erase prior navigation/request outliers, solve startup
content extraction, or verify every UI action. The overall goal remains open;
no main merge or live-server restart is included.

## Follow-on: reduce icon and history-button layout work

Recent-file history buttons now carry the action class directly, eliminating one
wrapper per recent row while keeping grouped-button styles elsewhere. JSON/lock
graphics use one shared CSS SVG; configuration files retain their distinct icon.
Fixed-size icon spans use inline blocks and centered SVGs instead of per-icon
flex layouts. Adjusted vertical alignment preserves the old 14px/13px graphic
baselines, and the old empty baseline pseudo-element is no longer necessary.
The 5,000 mixed-file fixture fell from **55,435 to 45,423 elements**, with its
pristine template still retained under the same four-scope/60,000-element bounds.

A fresh trace confirmed the startup cause again: Chrome's content extraction
enclosed a **143.09 ms Layout**, and took 153.26 ms overall. After wrapper/JSON
changes, those values were 127.42/134.22 ms; after simplifying icon layout,
120.78/127.04 ms. These traced runs add overhead and are diagnostic, not final
latency claims. Artifacts: `/tmp/lab-startup-layout-{baseline,simple,inline}-trace.json`
and corresponding result JSON files. All three still failed startup typing;
changing-file maxima were 71.50, 46.90, and 43.10 ms respectively.

A separate block-row experiment shifted filename baselines by 0.5 px and was
removed. Rows retain their original adaptive flex sizing. No browser feature was
disabled, no files hidden, and no input samples or startup phase discarded.

Validation: **41 sidebar checks passed** (39 in the full run, plus both Chrome
rendering cases after correcting the native Enter probe to send its character
event). The Chrome checks compare original/candidate icon boxes and filename
baselines, 19 icon families in both inline/flex contexts, symlinks, both themes,
100/125% zoom, 220/340px widths, and complete nested/flat 5,000-file trees. Native
mouse movement verifies actual hover states, colors, effective opacity and button
geometry with/without Git badges. Enter activates the focused history button
exactly once. File/history/modal clicks, native find, scrolling, folder toggles,
drag/context metadata, template equivalence/cache bounds and navigation races
still pass. The final side-by-side screenshot was also inspected and matched.
Logs: `/tmp/lab-startup-final-tests.log`, `/tmp/lab-startup-keyboard-tests.log`.

The fixture now accepts `--css-revision` as well as `--app-revision`, allowing
exact prior stylesheet/script comparisons without altering backend behavior.
Sequential untraced runs against `81fe1cf` and the candidate used fresh browsers,
normal lifespan/polling, 100 keys per phase and five fixture writes per loaded
phase:

| Fixture / version / phase | Median | p95 | Maximum | Keys at/above 50 ms |
| --- | ---: | ---: | ---: | ---: |
| Mixed, prior, normal | 7.10 ms | 27.40 ms | 99.30 ms | 3 |
| Mixed, candidate, normal | 2.50 ms | 24.20 ms | 62.60 ms | 2 |
| Mixed, prior, changing files | 3.00 ms | 28.80 ms | 48.90 ms | 0 |
| Mixed, candidate, changing files | 5.10 ms | 33.80 ms | 41.50 ms | 0 |
| SVG-heavy, prior, normal | 3.30 ms | 34.60 ms | 125.40 ms | 4 |
| SVG-heavy, candidate, normal | 5.00 ms | 30.90 ms | 130.90 ms | 4 |
| SVG-heavy, prior, changing files | 15.60 ms | 108.40 ms | 144.70 ms | 17 |
| SVG-heavy, candidate, changing files | 15.50 ms | 110.70 ms | 123.00 ms | 17 |

All four runs retained every key and verified final file mtimes and recent-file
ordering, without input, HTTP, network, browser or timestamp errors. API maxima
were 94.30, 45.20, 128.60 and 101.50 ms respectively. All four runs still fail the
overall typing budget. Mixed input improved in this comparison, but its loaded
median/p95 did not uniformly improve, and SVG-heavy startup remained worse in
this sample. Artifacts: `/tmp/lab-startup-final-{mixed-before,mixed-after,svg-before,svg-after}-{browser,server}.json`.

The SVG-heavy list (`ipynb,pdf,svg,js`) identifies a concrete remaining limit:
**85,435 prior / 80,423 candidate elements** exceed the 60,000-element template
bound, so neither retained a template. Its changed-file refreshes still cause
97–118 ms tasks. These fixtures exercise listing/rendering of those extensions;
their generated files were not opened or executed. Further reduction of inline
SVG structure is needed before fragment reuse can help this case; increasing
the cache limit would conceal the cause.

Final navigation passed 40 actions: workspace first/maximum **161.60 ms**, median
106.00 / p95 151.10 ms; document maximum **79.00 ms**, median 36.80 / p95 71.10 ms.
All 336 APIs stayed below **99.10 ms**, without HTTP, network, browser or input
timestamp errors (`/tmp/lab-startup-final-navigation-{browser,server}.json`). Every
owned echo terminal was removed. JavaScript syntax and `git diff --check` passed.
The goal remains open: startup/SVG-heavy typing misses, prior request outliers,
and unverified actions remain. No main merge or live-server restart is included.

## Follow-on: share the remaining file-icon graphics

All file icons now render one fixed-size span. The remaining fixed-color SVG
trees moved to shared CSS backgrounds. Image and generic-document icons use
currentColor masks, preserving inherited theme/Git colors. Configuration files
retain a separate glyph from JSON/lock: its strokes sit above theme-colored
circle interiors, including custom `--bg-primary` values. Symlink overlays,
file-type selection, icon boxes and text baselines stay intact. No external
asset requests, hidden rows, asynchronous rendering or cache-limit increases
were introduced.

The 5,000-file `ipynb,pdf,svg,js` fixture fell from **80,423 to 45,423 elements**.
Its pristine template now fits the existing four-scope/60,000-element bound,
allowing folder-fragment reuse during real file changes. A configuration-only
fixture (`toml,yaml,ini,cfg`) also retained a 45,423-element template.

Validation: **119 checks passed**, including both real-Chrome nested/flat
5,000-file cases, sidebar cache/navigation/config/dashboard tests and the full
terminal UI test file. A stale terminal test expected three inline sidebar
click handlers; it now checks the delegated handler and captured root introduced
in an earlier checkpoint. The existing linked-terminal call restrictions remain.
JavaScript syntax and `git diff --check` passed.

Original vectors are retained independently in
`core/tests/fixtures/file-icons-legacy.js`. Browser screenshots compare all 19
icon families, with/without symlinks, under dark/light/custom colors and 100/125%
zoom. At native scale, per-cell mean RGB differences were at most 0.066/255,
and the largest channel difference was 18/255, confined to edge compositing of
theme fills/masks. Tests cap those at 0.1 and 20 respectively. Fractional zoom
rasterizes CSS backgrounds differently from inline SVG; those screenshots were
inspected, and geometry/baseline checks pass. Native hover/Enter, file/history/
modal actions, Git badges, find-in-page and complete scrolling remain covered.
Artifacts: `/tmp/lab-all-icons-final-tests.log` and
`/tmp/lab-all-icons-final-qa/test_sidebar_offscreen_renderi{0,1}/sidebar*.png`.

Sequential untraced typing runs used exact `a54295a` JavaScript/CSS for the
baseline, fresh Chrome profiles, normal startup/polling, 100 keys per phase and
five fixture writes during the loaded phase:

| Fixture / version / phase | Median | p95 | Maximum | Keys at/above 50 ms |
| --- | ---: | ---: | ---: | ---: |
| SVG-heavy, prior, normal | 4.50 ms | 22.10 ms | 128.00 ms | 4 |
| SVG-heavy, candidate, normal | 3.60 ms | 22.80 ms | 112.20 ms | 3 |
| SVG-heavy, prior, changing files | 7.40 ms | 81.50 ms | 107.50 ms | 11 |
| SVG-heavy, candidate, changing files | 3.90 ms | 35.20 ms | 67.30 ms | 1 |
| Config-heavy, candidate, normal | 2.90 ms | 24.20 ms | 106.60 ms | 3 |
| Config-heavy, candidate, changing files | 3.20 ms | 36.10 ms | 84.20 ms | 4 |

The prior SVG-heavy run had five loaded 90–105 ms tasks; neither candidate had
a loaded task at/above 50 ms. Each candidate still had a 109 ms startup task.
All runs preserved all 200 keys and verified final file mtimes and recent-file
ordering, with no input, HTTP, network, browser or timestamp errors. Every owned
echo terminal was removed and every fixture server stopped. All three runs
still fail the 50 ms typing budget. Artifacts:
`/tmp/lab-all-icons-final-{svg-before,svg-after,config-after}-{browser,server}.json`.

An earlier candidate run also remains recorded: normal maximum 79.10 ms and
changing-files maximum 52.50 ms, with three total typing misses and all 97 APIs
below 100.50 ms (`/tmp/lab-shared-all-icons-{browser,server}.json`). It does not
replace the slower final samples.

Final API maxima were **86.60 / 202.20 / 127.50 ms** for prior SVG, candidate SVG,
and candidate config respectively, over 96/102/103 requests. The 202.20 ms miss
was `/api/workspace-files`. Timing/order correlation places its ASGI entry
150.49 ms after browser initiation and its final body 52.09 ms later; the
preceding overlapping file-list request took 184.34 ms inside ASGI. The next
browser file-list request took 195 ms. This suggests delay before ASGI entry,
but does not establish its cause; the endpoint already runs in a worker thread,
and these logs do not contain request IDs. No endpoint error or data loss was
observed. The request miss is retained for follow-up rather than excluded.

Both final navigation probes passed **80 actions each** (40 workspace and 40
document clicks). The ordinary fixture had workspace median/p95/maximum
67.50/73.80/**81.00 ms**, and document maximum **70.30 ms**; all 652 APIs were
below **50.60 ms**. The 5,000-file SVG-heavy fixture had workspace
103.20/121.30/**184.60 ms**, and document maximum **78.90 ms**; all 657 APIs were
below **144.20 ms**. Neither probe had browser, HTTP, network or budget errors.
Artifacts: `/tmp/lab-all-icons-final-navigation{,-large}-{browser,server}.json`.

This checkpoint makes changed-file refreshes cheaper across file types. Startup
typing, remaining loaded keystrokes, file-list queueing and previously recorded
outliers still need work, and every UI action has not been verified. The overall
goal remains active. No main merge, push or live-server restart is included.

## Follow-on: avoid notebook path resolution when nothing is running

The pending tracker previously resolved every notebook's complete path before
looking it up, including when the tracker was empty. `is_path_pending` now checks
for an empty registry under the existing lock and returns false immediately.
When any notebook is running, resolved-path matching and locking are unchanged.
No file data or pending state is cached, and no execution or kernel behavior is
changed.

The isolated timing fixture now appends an opt-in Server-Timing request ID and
records that same ID through browser ResourceTiming. This removes the ambiguity
between overlapping requests in the previous checkpoint's timestamp-only
correlation. Existing response headers and bodies are preserved; production
responses are unaffected. Handler tracing supports synchronous and asynchronous
routes, function tracing awaits coroutine completion, and `--trace-files` adds
file-list/mtime handlers, guarded scans, pending lookups and serialization.
ContextVars follow normal AnyIO worker dispatch; fsguard's independent workers
still have no request context, so their nested timings must not be blindly
summed across concurrent work.

Before the change, the mixed 5,000-file fixture's 1,250 notebook lookups consumed
**21.18–50.04 ms per scan**, within **36.56–81.45 ms** file-list handlers. The
entire trace recorded 15,000 lookups totaling 347.85 ms. Response serialization
was smaller (44.74 ms across 109 responses; maximum 8.00 ms). After the change,
the same lookups consumed **0.20–1.55 ms per scan**, with handlers ranging from
16.60 to 61.08 ms under normal background activity. Traced typing still failed:
normal/loaded maxima were 86.50/50.60 ms before and 83.90/52.20 ms after. All APIs
stayed under 128.90 ms before and 69.80 ms after. Traces are diagnostic, not a
claim that browser latency consistently improved. Artifacts:
`/tmp/lab-files-traced-before-{browser,server}.json` and
`/tmp/lab-pending-traced-after-{browser,server}.json`.

The scan comparator now accepts file extensions and loads the baseline's original
pending helper as well as its file-list route. It alternates implementations only
between completed samples in one isolated process and restores the helper on
exit. Twenty samples per variant retained every first sample and compared complete
responses against `cd38c1b`, including symlinks and metadata:

| 5,000-file fixture / transport | Prior median / maximum | Candidate median / maximum |
| --- | ---: | ---: |
| `ipynb,pdf,svg,js`, direct route | 34.65 / 37.51 ms | 12.64 / 20.64 ms |
| `ipynb,pdf,svg,js`, full ASGI | 40.87 / 44.59 ms | 18.57 / 20.90 ms |
| `ipynb`, direct route | 101.00 / 104.90 ms | 13.83 / 20.79 ms |
| `ipynb`, full ASGI | 108.05 / 120.70 ms | 19.96 / 24.10 ms |

Every comparison produced equal responses. Full ASGI here includes FastAPI
validation/serialization and worker dispatch in TestClient, not socket transport
or the normal server's complete middleware/lifespan. These are listing fixtures;
their generated notebook files were not executed. Artifacts:
`/tmp/lab-pending-scan-{mixed,notebooks}-{route,asgi}.json`.

Validation: **79 tests passed**, covering diagnostic fidelity/correlation,
notebook execution routes, workspace routes, empty-state filesystem avoidance,
queued runs, retargeted symlink identity and pending changes without file edits.
Concurrent sync/async diagnostics preserve responses and distinct request IDs;
error/stream behavior, pre-existing headers and coroutine exceptions are checked.
No original application headers or diagnostic arguments/bodies are logged.
Log: `/tmp/lab-pending-empty-tests.log`. Syntax and whitespace checks passed.

Separate untraced browser runs used fresh profiles, normal lifespan/polling, all
100 keys in each phase and five verified fixture-file writes:

| Fixture / version / phase | Median | p95 | Maximum | Keys at/above 50 ms |
| --- | ---: | ---: | ---: | ---: |
| Mixed, prior, normal | 3.20 ms | 25.60 ms | 103.40 ms | 3 |
| Mixed, candidate, normal | 2.80 ms | 22.40 ms | 101.20 ms | 3 |
| Mixed, prior, changing files | 6.70 ms | 27.80 ms | 44.50 ms | 0 |
| Mixed, candidate, changing files | 6.50 ms | 39.50 ms | 62.80 ms | 3 |
| Notebooks, candidate, normal | 3.30 ms | 24.00 ms | 97.30 ms | 2 |
| Notebooks, candidate, changing files | 4.20 ms | 46.50 ms | 81.40 ms | 5 |

All three runs still fail the typing target. In particular, loaded mixed typing
was worse in this sample; backend improvements do not establish better input
latency. All input, HTTP, network, browser and timestamp checks passed, and all
API requests correlated to server IDs. API maxima were **144.00 / 133.70 /
133.40 ms** over 104/104/103 requests. Every owned terminal was removed and each
fixture server stopped. Artifacts:
`/tmp/lab-pending-empty-{before,after,notebooks}-{browser,server}.json`.

The 5,000-file navigation fixture passed all **80 clicks**: workspace
median/p95/maximum **113.30/121.20/155.50 ms**, document maximum **68.70 ms**.
All 657 APIs stayed below **49.00 ms**, with no browser, HTTP or network errors
(`/tmp/lab-pending-empty-navigation-{browser,server}.json`).

This checkpoint removes measured idle-notebook scan work. Startup and loaded
typing still miss 50 ms, the earlier 202.20 ms file-list request and other
outliers are not proven resolved, and the nonempty pending registry retains its
previous cost. The full goal remains active. Main merge/push and live-server
restart are not included.

## Follow-on: prepare sidebar layout in short idle callbacks

The current build still reproduced Chrome's native extraction pause: a
**126.73 ms** content build enclosed **120.54 ms** of forced layout, causing
130.30 ms typing latency in a trace. Grid file rows preserved geometry but made
that layout **141.15 ms**, so they were removed. Filename inline-size containment
left **107.05 ms** of layout and was also removed. The final implementation keeps
the original flex rows and their adaptive sizing.

After mounting, the sidebar now prepares one existing recent-file group per idle
callback. A live `data-sidebar-layout-ready` attribute changes that group's
content visibility from auto to visible, allowing later native search/content
extraction to inspect already-laid-out rows. Every file remains present; browser
features, accessibility and native find are preserved. This spreads work rather
than claiming less total CPU. Containers above 200 direct children remain on
normal layout, so this is not a bound for every possible tree shape.

Jobs verify the mounted first/last children, child count, connection and page
visibility. Replacements cancel prior callbacks and release all retained DOM
references. Closed folders stay unprepared; opening a folder or making the page
visible resumes preparation. Markers never enter pristine templates. An attribute
is necessary because anonymous flat groups use their class as their reconciliation
key. The existing four-scope/60,000-element cache bounds remain unchanged.

Native drag checks caught a regression before the checkpoint: prepared groups
increased median/maximum sidebar drag time from **26.90/35.20 ms** to
**143.80/150.20 ms**. Preparation now resets at sidebar drag start and window
resize, stays suspended during dragging, and resumes after release. Final native
drags measured **17.50 ms median / 30.30 ms maximum**. Their 10 workspace and 10
document clicks also passed (147.40 / 68.70 ms maxima); all 183 APIs stayed below
54.80 ms. The new `--resize` probe timestamps mouse-down through release without
waiting for renderer acknowledgments between events, verifies the actual width,
and includes the final rendered frame. Artifacts:
`/tmp/lab-idle-layout-resize-{before,after,fixed}-{browser,server}.json`.

Validation: **120 tests passed**, including real Chrome checks for 5,000-file
nested and flat trees, geometry, native find, scrolling, hover/keyboard/actions,
themes/zoom, icons and Git badges. Prepared rows retain identity/focus across
changed-file reconciliation; stripping only live preparation markers produces
the exact full-render DOM, and cached templates remain pristine. Scheduler tests
cover stale callbacks, job replacement, hidden/disconnected views, closed folders,
unsupported browsers, width invalidation and suspension during drag. The final
side-by-side screenshot was inspected. Logs/screenshots:
`/tmp/lab-idle-layout-final-tests.log` and `/tmp/lab-idle-layout-final-qa/`.

The typing probe now retains buffered long tasks and starts optional tracing
before Page.navigate, so moving work before terminal readiness cannot conceal a
new startup pause. The final full-startup trace had **54 idle callbacks**, maximum
**18.37 ms**, totaling 249.62 ms. Largest Layout was **14.23 ms**. Chrome's later
content build took **18.17 ms**; its former single 120 ms layout did not recur.
A **67 ms** task before terminal readiness is still recorded, as are all later
input samples. Traced normal/loaded typing maxima were 37.50/53.20 ms and all
107 APIs stayed below 45.10 ms. Artifact:
`/tmp/lab-idle-layout-trace-fixed.json` plus matching browser/server sidecars.
Earlier experiments are retained at `/tmp/lab-row-layout-{before,grid,contained,prime}-*`.

Untraced comparisons used exact `786afb9` JavaScript/CSS for the prior version,
fresh browsers, 5,000 `ipynb,pdf,svg,js` files, every one of 100 keys per phase,
and five verified fixture writes during the loaded phase:

| Version / layout / phase | Median | p95 | Maximum | Keys at/above 50 ms |
| --- | ---: | ---: | ---: | ---: |
| Prior, nested, normal | 3.40 ms | 23.50 ms | 86.00 ms | 2 |
| Candidate, nested, normal | 11.60 ms | 26.70 ms | 43.20 ms | 0 |
| Candidate, flat, normal | 12.10 ms | 27.10 ms | 37.20 ms | 0 |
| Prior, nested, changing files | 3.40 ms | 36.20 ms | 85.40 ms | 2 |
| Candidate, nested, changing files | 12.00 ms | 48.10 ms | 59.90 ms | 4 |
| Candidate, flat, changing files | 3.80 ms | 42.80 ms | 55.60 ms | 2 |
| Final resize-safe candidate, nested, normal | 10.60 ms | 27.70 ms | 30.90 ms | 0 |
| Final resize-safe candidate, nested, changing files | 10.10 ms | 42.00 ms | 66.20 ms | 3 |

Normal typing met 50 ms in these candidate runs, but medians/p95 did not uniformly
improve and loaded typing still failed. All keys/file changes were verified,
without input, HTTP, network, browser or timestamp errors. API maxima for the
four untraced runs were 116.70/148.50/102.40/115.60 ms over 104/104/105/103 requests;
all correlated to server IDs. Every owned terminal was removed and fixture server
stopped. Artifacts: `/tmp/lab-idle-layout-final-{before,after,flat}-{browser,server}.json`
and `/tmp/lab-idle-layout-typing-fixed-{browser,server}.json`.

Separate nested/flat navigation runs passed **80 clicks each**. Workspace maxima
were **161.40 / 151.80 ms**, document maxima **71.10 / 63.40 ms**, and all 660/657
APIs stayed below **76.50 / 76.00 ms**. Artifacts:
`/tmp/lab-idle-layout-final-navigation{,-flat}-{browser,server}.json`.

Remaining work includes changing-file typing, the pre-readiness task, earlier
request outliers, larger/unusual tree shapes and UI actions not yet measured.
The overall goal remains active. No main merge, push or live-server restart is
included.


## Checkpoint: render background sidebar data once

The 5,000-file loaded typing profile still spent **344.02 ms** in sidebar refresh
stacks during 5.09 seconds of sampling. Cached background refreshes generated the
old tree immediately and generated another tree when fresh data differed. This
could place two 15–35 ms render tasks near the same input/render frame.

Mtime polling and live index updates now explicitly request `backgroundRefresh`.
For a cached workspace, they retain the mounted rows during the fresh read and
render once afterward. User navigation/settings retain immediate cached paint.
Equal fresh data still renders once: notebook grace expiry, viewed markers,
selection and folder state can change without different file metadata. Failed
file reads render the cached payload only if the same generation, workspace and
selected worktree still own the sidebar. Dashboard reads retain their shared
batch and stale-response guards. No file data or browser functionality is hidden,
and template/cache bounds are unchanged.

The controlled typing probe requests the same production background mode. Exact
`4d10266` ignores that additional option and therefore remains a valid prior-code
comparison. The refresh promise has always returned before detached fresh-data
reconciliation; its diagnostic is now named `dispatchMs` to avoid calling that
full refresh latency. Cache mtimes and visible recent ordering are independently
verified after fixture writes.

**148 regression tests passed**, including 28 additional background/cached-read
and dashboard cases. They cover changed/equal data, failed reads, immediate user
navigation, old responses/fallbacks after workspace/worktree/newer-refresh changes,
and one dashboard request batch. Existing real-Chrome checks cover full large
nested/flat trees, native find, focus, file/history actions, icons, Git decorations,
folder state and resize invalidation. Log and artifacts:
`/tmp/lab-background-refresh-tests.log`, `/tmp/lab-background-refresh-qa/`.

Untraced fresh-browser runs retained every one of 100 keys per phase, normal
polling, 5,000 `ipynb,pdf,svg,js` files and five verified changes during loaded input:

| Version / layout / phase | Median | p95 | Maximum | Keys at/above 50 ms |
| --- | ---: | ---: | ---: | ---: |
| Prior, nested, normal | 6.30 ms | 25.40 ms | 28.70 ms | 0 |
| Candidate, nested, normal | 4.90 ms | 26.80 ms | 37.90 ms | 0 |
| Candidate, flat, normal | 10.30 ms | 30.70 ms | 38.00 ms | 0 |
| Prior, nested, changing files | 9.30 ms | 32.00 ms | 52.20 ms | 1 |
| Candidate, nested, changing files | 5.50 ms | 26.60 ms | 46.50 ms | 0 |
| Candidate, flat, changing files | 3.50 ms | 23.80 ms | 40.50 ms | 0 |

API maxima were **58.70 / 107.80 / 94.80 ms** across 99/99/91 requests. All were
correlated with the isolated server; there were no input, timestamp, HTTP,
network or browser errors. The startup long task remains: 59/58/53 ms, all before
terminal readiness and retained in output. Artifact prefix:
`/tmp/lab-background-refresh-{before,after,flat}-{browser,server}.json`.

A matched CPU/timeline profiling run reduced inclusive sampled sidebar refresh
work from **344.02 to 190.31 ms** over 5.09/5.05-second windows (about 45%). Recent
section rendering fell 79.04→32.89 ms; normal file-tree rendering 60.87→24.97 ms.
Idle layout work did not disappear (141.17→155.22 ms). Profiling-run typing maxima
were 37.70 ms normal / 46.40 ms changing files, with all 102 APIs below 107.30 ms.
The separate untraced results above are the responsiveness evidence. Profiles:
`/tmp/lab-refresh-4d-profile.json`, `/tmp/lab-background-refresh-profile.json`;
trace/browser/server sidecars use `/tmp/lab-background-refresh-{trace,profile-*}`.

Native navigation/resize checked **40 workspace clicks, 40 document clicks and
40 sidebar drags**. Maxima were **166.20 / 71.40 / 27.50 ms**, respectively; all
672 APIs were below **62.30 ms**, without errors or budget misses. Artifact:
`/tmp/lab-background-refresh-navigation-{browser,server}.json`.

A longer untraced run retained **600 keys** (300 per phase), **15 verified file
updates** and further normal polling cycles. Normal typing had median/p95/max
**3.40/23.80/47.10 ms**. Loaded typing was **3.40/26.90/52.60 ms**, with **two
misses**: 52.60 ms (1.10 ms input queue, 51.50 ms handler-to-render) and 50.50 ms
(22.70 ms queue, 27.80 ms handler-to-render). The first missed key parsed 41.90 ms after
its handler, with another 9.60 ms until render; this run has no timeline trace to
assign that delay to a specific task. All 231 APIs were below **84.60 ms**; there
were no correctness, browser, network, HTTP or timestamp errors. Its 57 ms startup
long task remained in the record before readiness. Artifacts:
`/tmp/lab-background-refresh-sustained-{browser,server}.json`.

All six fixture servers stopped and their owned terminals (typing runs) were
removed. Every recorded API correlated to a matching server ID and route. The
short passing runs do **not** establish sustained compliance: changing-file
input still occasionally exceeds 50 ms. Remaining work also includes the startup
task, prior request outliers, larger/unusual trees, and unmeasured UI actions.
The overall goal remains active. This checkpoint includes no main merge, push
or live-server restart; the earlier merge approval remains pending.


## Checkpoint: transfer unchanged detached sidebar folders

A sustained 600-key trace of `e5c6256` reproduced a **60.40 ms** loaded input
(32.10 ms queued before its handler, 28.30 ms afterward). The overlapping sidebar
refresh sampled **39.44 ms**, including **13.11 ms** in `cloneNode`; the subsequent
frame spent **19.21 ms** in lifecycle work, including 12.48 ms pre-paint. Source
folders were already known equal, but assembling the next pristine template
still deep-cloned them. The trace is `/tmp/lab-sustained-e5-trace.json`, with
matching profile/browser/server sidecars. Its separate 60 ms startup task remains.

The builder now places temporary references to unchanged detached folders,
reconciles the visible sidebar while the old source template is intact, then
transfers those folders from the retired cache entry into the new pristine
entry. This avoids copying tens of thousands of unchanged nodes. Changed/new
parents and mismatched live containers expand references in their fallback
clones; whole-sidebar fallback uses the fully assembled template. Expanded element
counts are computed before reconciliation so oversized trees take the existing
complete, uncached path. Explicit navigation still mounts pristine clones. The
four-scope/60,000-element limits and all live row decorations/actions remain.

**148 targeted tests passed**, including real Chrome coverage. The template test
now verifies unchanged folder identity transfers without parsing/deep cloning,
30 changed/reordered ancestors, exact full-parse equivalence, expanded element
counts, focus/Git state, invalidated live containers and whole-sidebars, newly
introduced parents, literal placeholder-like content, explicit navigation and
oversized transitions. Both 5,000-file nested/flat native action/rendering checks
passed. Log and artifacts: `/tmp/lab-template-transfer-tests.log` and
`/tmp/lab-template-transfer-qa/`.

Matched 15-second CPU/timeline profiles, 300 keys per phase and 15 file updates,
showed inclusive sidebar refresh sampling falling **632.72→358.99 ms**. Template
building fell **154.00→50.54 ms** and `cloneNode` samples **109.21→0.00 ms** (zero
samples is not a claim that no small live clones occur). These are separate
profiled runs, not deterministic CPU totals; the no-deep-clone regression checks
establish the intended mechanism. Candidate traced typing maxima were **33.50 ms
normal / 45.00 ms loaded**. Profile artifacts:
`/tmp/lab-sustained-e5-profile.json`, `/tmp/lab-template-transfer-profile.json` and
`/tmp/lab-template-transfer-trace.json`.

Untraced comparisons kept all **600 keys** per run, **15 verified file writes**,
normal polling and 5,000 `ipynb,pdf,svg,js` files:

| Version / layout / phase | Median | p95 | Maximum | Keys at/above 50 ms |
| --- | ---: | ---: | ---: | ---: |
| Prior `e5c6256`, nested, normal | 4.00 ms | 23.50 ms | 30.70 ms | 0 |
| Candidate, nested, normal | 3.80 ms | 23.40 ms | 48.50 ms | 0 |
| Candidate, flat, normal | 3.90 ms | 26.20 ms | 40.40 ms | 0 |
| Prior `e5c6256`, nested, changing files | 6.50 ms | 215.10 ms | 590.10 ms | 22 |
| Candidate, nested, changing files | 6.90 ms | 26.90 ms | 41.70 ms | 0 |
| Candidate, flat, changing files | 7.70 ms | 223.00 ms | 600.00 ms | 22 |

The **590/600 ms failures are retained and unresolved**. They occurred on both
versions, so the passing nested candidate does not establish a fix. In the flat
candidate, the first affected key left Chrome 1.18 ms after its external input
timestamp; subsequent keys continued to leave throughout the pause. No echo
frame arrived until **599.71 ms** after that key, when a 24-character frame arrived
and parsed immediately. Most key handlers were prompt, and HTTP requests continued
completing in a few milliseconds during the prior-version stall. This points the
next investigation toward terminal transport/server/PTY/tmux, separately from
the browser rendering optimization; the exact cause is not yet identified.

The probe now records CDP WebSocket frame timestamps, direction, type, length and
resize geometry for only its owned echo terminal. It stores no frame payloads or
credentials. Automatic terminal-query replies are retained but excluded from
native one-letter key counts. The first profiled diagnostic incorrectly counted
four startup replies as keys and exited nonzero despite all 600 measured keys
passing; that failed artifact is retained. The corrected flat probe verified
all 600 key frames and had no diagnostic error, while correctly failing the
latency gate on the 22 delayed keys.

The three untraced runs had 226/229/231 APIs, maxima **75.70/57.80/93.50 ms**.
The prior/candidate profile runs had 247/233 APIs, maxima **80.60/96.30 ms**.
All requests correlated to matching server IDs/routes, with no HTTP, browser,
network, input-content or timestamp errors. Startup tasks of **53–60 ms** remain
recorded before readiness. Files/cache mtimes and recent ordering were verified.
Artifacts: `/tmp/lab-template-transfer-{before,after,flat,profile}-{browser,server}.json`.

Native navigation/resize passed **40 workspace clicks, 40 document clicks and
40 drags**, with maxima **195.80/61.20/27.80 ms**. All 669 APIs were below **74.70 ms**.
The first workspace click is close to budget and is retained. Artifact:
`/tmp/lab-template-transfer-navigation-{browser,server}.json`.

All six fixture servers stopped; all five owned typing terminals were removed.
The overall goal remains active: terminal transport stalls, remaining startup
work, earlier request outliers, broader actions and iTerm comparison still need
work. This checkpoint includes no main merge, push or live-server restart.


## Checkpoint: trace terminal transport and match production WebSocket settings

The fixture's direct `uvicorn.Config` used its default WebSocket compression,
while `core.main.run()` explicitly disables permessage-deflate. The fixture now
matches production (`ws_per_message_deflate=False`, graceful shutdown timeout 5 s).
`--websocket-deflate` retains the prior setting as an explicit diagnostic
comparison. Chrome records the owned terminal's handshake status and negotiated
compression bit and fails if they differ from the requested configuration.
No cookie/header values or frame payloads enter the report. Production code and
the live server are unchanged by this checkpoint; this repairs measurement parity.

`--trace-terminal` adds fixture-only timestamps at WebSocket receive/send and at
term.py's PTY reads/writes. Connection context identifies only descriptors created
for traced terminal connections. Module-local proxies leave global `os`/`pty`
untouched and restore the original dependencies after shutdown. Traces preserve
short writes, byte counts, exceptions and frame identity; only metadata is stored.
Closed descriptors lose their association. Unrelated WebSockets and normal
untraced operation retain their original calls.

The owned raw echo process can also timestamp its read and write in memory. It
exports metadata after the browser run, on SIGUSR1, so file logging does not delay
measured input. The controller checks its recorded PID against the still-owned
fixture pane before signaling. Export failures still go through terminal cleanup.
This separates input reaching tmux, reaching the application, and returning from
tmux into the server's bridge. **16 diagnostic regression tests passed**, including
real raw-PTY echo with/without tracing, payload privacy, simultaneous connection
contexts, short writes/errors, failed sends, descriptor reuse, dependency cleanup,
and refusal to signal a PID that no longer owns the fixture pane.

The half-second stall was reproduced with per-stage tracing in explicit compressed
mode, retaining **22 missed keys**, maximum **581.80 ms**. Relative to the first
affected native input:

| Observation | Time after input |
| --- | ---: |
| Server received input frame | 2.410 ms |
| Server completed one-byte PTY write | 2.439 ms |
| First subsequent PTY read (24 accumulated bytes) | 581.390 ms |
| Server started echo frame send | 581.412 ms |
| xterm finished parsing that key | 581.600 ms |
| xterm rendered that key | 581.800 ms |

Other keys kept arriving at the server and completing PTY writes throughout that
interval. The server's echo send took 0.021 ms. Thus this captured stall occurs
between the bridge's PTY write and return read, not in HTTP handling, browser
input queueing, or the final WebSocket send/render. The responsible component
inside that interval is **not yet identified**; compression was present but is
not established as the cause. An echo-process trace was added afterward and did
not reproduce the half-second stall in its two runs. The fixture still uses its
owned session on the shared default tmux server, so server contention remains a
possible factor to test with a separately owned socket, not an established cause.

A different compressed run retained a **52.20 ms normal-typing miss**. Its echo
program read/wrote at 1.484/1.503 ms, the bridge read at 1.654 ms, and xterm parsed
at about 1.7 ms, then rendered at 52.2 ms. This is a separate browser render delay;
the new measurements prevent confusing it with the PTY stall.

All runs retained every key and verified changing file mtimes/recent ordering in
the 5,000-file flat `ipynb,pdf,svg,js` fixture with normal polling:

| Run / transport / tracing | Keys | Normal max | Loaded max | Misses ≥50 ms | API max |
| --- | ---: | ---: | ---: | ---: | ---: |
| Initial legacy defaults / bridge trace | 1,200 | 43.80 ms | 43.70 ms | 0 | 171.50 ms |
| Longer legacy defaults / bridge trace | 2,000 | 40.70 ms | 49.40 ms | 0 | 175.30 ms |
| Explicit compressed / bridge trace | 600 | 32.90 ms | 581.80 ms | 22 | 74.50 ms |
| Production uncompressed / bridge trace | 600 | 42.90 ms | 45.00 ms | 0 | 87.70 ms |
| Production uncompressed / bridge + echo trace | 600 | 36.60 ms | 40.50 ms | 0 | 161.70 ms |
| Explicit compressed / bridge + echo trace | 600 | 52.20 ms | 43.10 ms | 1 | 101.10 ms |
| Final production uncompressed / byte tracing off | 1,200 | 35.20 ms | 51.90 ms | 1 | 103.00 ms |

The final untraced-byte run kept **30 file updates** and **422 APIs**. Its normal
median/p95 were 3.70/22.90 ms and loaded median/p95 5.40/24.10 ms. The missed key
queued **24.10 ms** before its handler and took **27.80 ms** afterward; it occurred
at the first loaded refresh. This remains a failing typing-budget result, not
sustained compliance. The 59 ms pre-readiness task also remains recorded. The two
echo traces exported all 600 bytes each; one coalesced read correctly represented
two keys. Chrome verified compression on/off for all runs after the handshake
instrumentation was added.

All seven fixture servers stopped and their owned terminals were removed. All
API records matched server IDs/routes. There were no input-content, timestamp,
HTTP, network, browser, handshake or diagnostic errors in these runs. Artifact
prefixes (each with `-browser.json`, `-server.json`, `.log`):
`/tmp/lab-terminal-path-before`, `/tmp/lab-terminal-path-long`,
`/tmp/lab-terminal-compressed`, `/tmp/lab-terminal-uncompressed`,
`/tmp/lab-terminal-echo`, `/tmp/lab-terminal-echo-compressed`,
`/tmp/lab-terminal-production-final`.

The overall goal remains active. Both PTY stalls and browser render misses need
further work; broader UI actions and prior API outliers are still unproven. This
checkpoint includes no main merge, push, production change or live-server restart.

## Checkpoint: retain containment after sidebar layout preparation

The production-matching 1,200-key trace at `179e056` passed the typing budget,
but one 49.6 ms key waited behind Chrome's own hit testing. Its overlay and sticky
ad detectors spent 17.94 + 7.60 ms checking the page. These are browser tasks,
not Lab timers; the benchmark keeps them enabled.

Idle preparation previously changed recent-file groups from
`content-visibility:auto` to `visible`, also removing auto's implicit layout,
style and paint containment. Prepared groups now explicitly retain those three
boundaries. Their content remains fully laid out and searchable. No size
containment, virtualization, fixed row height, input delay or scheduling change
was introduced. The CSS containment specification defines auto's implicit
boundaries and their persistence when its content is visible:
[CSS Containment Level 2](https://www.w3.org/TR/css-contain-2/#content-visibility).

Matched traces used 5,000 flat mixed notebook/PDF/SVG/JavaScript files, 600 keys
per phase, 30 real document writes during loaded typing, normal polling, and
production's uncompressed WebSockets. Both enabled browser/CPU/bridge/echo tracing.
Trace totals below include events after terminal readiness, not startup:

| Measured work | Before | Containment retained |
| --- | ---: | ---: |
| Paint total / largest event | 501.90 / 5.05 ms | 266.44 / 0.85 ms |
| PrePaint total / largest event | 350.36 / 9.93 ms | 229.23 / 6.02 ms |
| HitTest total / largest event (58 each) | 324.61 / 17.93 ms | 278.94 / 15.30 ms |
| Idle preparation total / largest callback | 194.54 / 4.72 ms | 144.72 / 3.56 ms |
| Quiet typing median / maximum | 4.50 / 49.60 ms | 4.20 / 33.80 ms |
| Loaded typing median / maximum | 5.30 / 45.90 ms | 4.50 / 47.80 ms |
| API maximum (454 each) | 73.50 ms | 91.90 ms |

Paint time fell about 47%, but the loaded maximum did not improve in this pair.
There were no missed keys, content/order/focus errors, dropped inputs, timestamp
errors, network/browser/HTTP failures or handshake mismatches. All 1,200 input
bytes reached each echo process; every API record matched a server ID and route.
Both fixture servers stopped and owned terminals were removed. Startup long tasks
of 63 and 58 ms remain in the reports. Artifacts:
`/tmp/lab-current-179-{browser,server,profile,trace}.json` and
`/tmp/lab-contained-{browser,server,profile,trace}.json`.

**160 targeted regression tests passed**, covering sidebar caches, stale navigation,
file configuration, dashboard refreshes, terminal links/UI/lifecycle/resources and
the native Chrome rendering checks. The latter retain complete 5,000-row nested
and flat trees, file/history/modal actions, keyboard Enter, focus through refresh,
native find, symlink/icon geometry, Git state, folder expansion, themes and zoom.
New comparisons cover first/last rows and both sides of 100-row group boundaries
with a focused history button and terminal-drop highlight, at two widths, two
zooms and both themes (64 total cases). They compare auto and prepared geometry,
hit targets and painted pixels. Initial exact-PNG checks found only antialiasing
differences (one failure was six corner pixels with a maximum channel difference
of four); the final check uses the existing small icon-edge tolerance. Maximum
mean channel difference was 0.009, maximum individual channel difference 15/255,
and at most 26 pixels differed in a case. Screenshots were also visually checked.
Artifacts: `/tmp/lab-contained-checks.log` and `/tmp/lab-contained-checks/`.

Untraced sustained checks (no browser/CPU/byte tracing) also used 600 keys per
phase and 30 real document writes each:

| Fixture | Quiet median / maximum | Loaded median / maximum | API count / maximum |
| --- | ---: | ---: | ---: |
| 5,000 mixed flat files | 2.90 / 35.60 ms | 7.10 / 33.30 ms | 436 / 61.60 ms |
| 5,000 mixed nested files | 3.60 / 34.40 ms | 5.00 / 43.30 ms | 416 / 95.90 ms |

All 2,400 keys passed 50 ms, and all 852 measured API requests passed 200 ms.
All content, order, focus, native-input timestamps, socket frames, server-ID/route
correlation and cleanup checks passed. No network, HTTP or browser errors occurred.
Artifacts: `/tmp/lab-contained-flat-{browser,server}.json` and
`/tmp/lab-contained-folders-{browser,server}.json`, with corresponding `.log` files.

Native navigation/resize verification retained all 60 actions, including cold
first clicks: workspace maximum **149.50 ms** (20 samples), document maximum
**67.60 ms** (20), and sidebar-drag maximum **30.40 ms** (20). All 344 API requests
passed 200 ms, maximum **70.40 ms**, with matching server IDs/routes and no browser,
HTTP or network errors. The fixture server stopped. Artifacts:
`/tmp/lab-contained-navigation-{browser,server}.json` and corresponding `.log`.

The full goal remains active. The untraced typing reports still contain startup
tasks of 54–65 ms. Previous intermittent PTY stalls, earlier API outliers, broader
UI actions, and physical comparison with iTerm remain unresolved or unmeasured.
Passing these finite samples does not establish a universal latency guarantee.
This checkpoint includes no main merge, push or live-server restart; the earlier
explicit merge-approval question remains pending after automatic review rejection.

## Checkpoint: show the new workspace tab without waiting for catalog polling

The new native creation probe found a UI overrun outside the previous navigation
coverage. Opening the + picker, choosing New workspace and selecting a vault were
fast. Submitting a name created and opened the workspace, but the new tab waited
for the next five-second catalog poll. `submitVaultWorkspace` refreshed
`workspacesList`; `workspaceTabsRender` uses the independent `workspaceTabsAll`.
The first measured POST returned in 80.7 ms and the post-create catalog in 2.3 ms,
but the workflow did not have its new workspace tab until **4,688.7 ms**.

After successful creation and its authoritative catalog refresh, the UI now adds
the confirmed row to the tab collection before normal navigation. It checks the
absolute path to prevent duplicates and preserve same-ID workspaces in other
vaults. Existing tab objects, pending state and order remain intact. The CLI,
creation API, persisted workspace format, captured vault, validation, error UI,
missing-row fallback, catalog polling and automatic terminal preference behavior
are unchanged.

`lab_navigation_latency.py --create --samples N` measures four native click
stages per workspace, including the final dashboard **and tab** through a rendered
frame. It uses an authenticated disposable vault, production polling and server
lifecycle. Its known future workspace IDs have automatic agent startup disabled
through the preferences API before the browser starts. All created data stays in
that temporary vault. The probe validates original tab order, unique created paths,
workspace names/IDs, initial task data, saved open flags and workspace directories.
Optional server timings include the actual POST handler and its CLI subprocess;
all HTTP samples, failures and over-budget actions are retained.

| Native action | Before maximum (5 each) | Candidate maximum (20 each) |
| --- | ---: | ---: |
| Open + picker | 35.3 ms | 40.0 ms |
| Choose New workspace | 37.1 ms | 39.8 ms |
| Open the name form | 56.0 ms | 56.5 ms |
| Create and open workspace with its tab | 4,688.7 ms | 185.3 ms |

Creation median fell from **4,383.0 ms** to **154.2 ms**. The baseline retains all
five missed creation actions; all 80 candidate actions passed 200 ms. All 230
baseline API requests passed 200 ms (maximum 139.7 ms), as did all 553 candidate
requests (maximum 105.0 ms). Server POST times were 69.5–100.8 ms before and
68.1–104.0 ms after; no backend speedup is claimed. All API IDs/routes correlated,
all correctness checks passed, and both fixture servers stopped without browser,
HTTP or network failures. Artifacts:
`/tmp/lab-create-before-{browser,server}.json` and
`/tmp/lab-create-after-{browser,server}.json`, with corresponding `.log` files.

**48 targeted tests passed** for picker creation, tab order/navigation, workspace
rename/delete/resources, mutations and vault routes. Added creation cases retain
the selected vault while it changes elsewhere, wait for the old catalog to settle,
make the confirmed tab available before navigation, preserve other tab identities
and flags, avoid duplicates if polling already found the row, and avoid ghost tabs
on failed creation or a missing post-create catalog row. Test log:
`/tmp/lab-create-tests.log`.

The larger-fixture follow-up kept 5,000 mixed notebook/PDF/SVG/JavaScript files in
each of the two existing workspaces and created 20 more through the native UI.
All 80 actions passed: creation median **151.1 ms**, maximum **178.9 ms**; picker,
vault-choice and form maxima **38.2 / 39.2 / 56.6 ms**. All 556 API requests passed,
maximum **111.1 ms**, with correct server-ID/route correlation and no browser,
network or HTTP failures. Original tabs stayed in order, each new tab appeared
once, and all created metadata/task files, saved open flags and docs/notes/assets
directories were verified. The fixture server stopped normally. Artifacts:
`/tmp/lab-create-large-{browser,server}.json` and `/tmp/lab-create-large.log`.

The overall goal remains active. These creation checks use empty new workspaces
and deliberately disable automatic agent startup in fixture preferences; they do
not establish agent-launch, notebook/server-control, all-vault-scale or physical
terminal latency. Previous PTY stalls, startup tasks, API outliers and other UI
actions still require work. No main merge, push or live-server restart is included;
the earlier merge-approval question remains pending after automatic review rejection.
