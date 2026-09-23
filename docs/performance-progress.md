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

## Checkpoint: measure scoped settings saves and complete sidebar updates

Added `lab_navigation_latency.py --settings`, using the same disposable CLI-created
vault, normal server lifecycle and UI polling. It opens Alpha, then repeatedly
opens the settings center, edits Beta's model without switching the active
workspace, selects Alpha's file preferences, toggles Recently updated visibility,
saves and closes. Every measured click retains its externally supplied native
timestamp and waits through the relevant rendered result. Sidebar saves wait for
the complete recent-row count to disappear or return, not just the Saved toast.
The final checks read both workspace metadata files and browser preference storage.

Form text uses CDP input. Select-option values are prepared before the native Save
click; this setup is not measured or claimed as native dropdown latency. Two early
attempts using page-CDP arrow/Space/Enter events did not commit the native macOS
select popup and stopped with an explicit error. Their earlier click samples remain
in `/tmp/lab-settings-large-before-browser.json` and
`/tmp/lab-settings-choice-browser.json`; neither is counted as a complete benchmark.
No production behavior changed in this checkpoint.

The initial small-fixture run covered 41 clicks, including 10 cycles of opening,
inactive-scope selection, model save and close. Maxima were **53.4 / 54.5 / 53.4 /
37.4 ms** respectively; the first workspace open took **64.2 ms**. All 197 API
requests passed 200 ms, maximum **43.6 ms**. Scope, persisted model and unchanged
agent checks passed. Artifacts: `/tmp/lab-settings-before-{browser,server}.json`.

The expanded CPU-profiled flat 5,000-file run retained all 71 actions. Its 10 full
sidebar preference saves peaked at **107.5 ms**, but the cold workspace open missed
at **214.7 ms**. All 300 API requests passed (maximum **99.8 ms**). The first file-list
request took 97.5 ms server-side, followed by roughly 58.4 ms of sampled sidebar
rendering (46.3 ms in template assembly/mounting). Clean Git decoration application
also sampled at 8.3 ms early in that interaction. These are separate contributors;
the miss is retained, not explained away by the passing settings operations.
Artifacts: `/tmp/lab-settings-redraw-{browser,server,profile}.json`.

Optional `LAB_PERF_TRACE` now captures navigation from before Page.navigate, using
the same Blink/display-lock categories as the terminal probe. Reports also include
`timeOrigin`, so native sourceEpoch and trace navigation-relative times can be
aligned directly. A follow-up with full tracing plus file-function timings recorded
173.0 ms for the cold open (35.7 ms file request; 28.2 ms guarded scan; 2.0 ms response
serialization), but two Hide recent saves took **354.8 / 372.8 ms**. Its CPU profile
sampled 603.8 ms in reconciliation, including 330.9 ms removing DOM, across the run.
The trace also retained a 73.8 ms Chrome AI-content extraction with 65.9 ms layout.
These heavily instrumented results are labeled separately; untraced verification
is required before attributing that removal cost to normal use. Artifacts:
`/tmp/lab-settings-cold-{browser,server,profile,trace}.json`.

All three complete runs above matched browser API IDs/routes to server records,
had no HTTP/network/browser errors, and stopped their fixture servers normally.

The final untraced check retained **141 actions**, including the first cold open
and 20 complete settings cycles with 5,000 flat mixed files:

| Action | Maximum |
| --- | ---: |
| Cold workspace open (one sample) | 182.7 ms |
| Open settings | 82.2 ms |
| Select inactive Beta | 75.3 ms |
| Save Beta's model and show refreshed form | 66.8 ms |
| Select active Alpha | 55.5 ms |
| Open File sidebar preferences | 41.8 ms |
| Save preference and finish sidebar row update | 124.1 ms |
| Close settings | 41.4 ms |

All actions passed 200 ms. All **589 API requests** passed, maximum **67.5 ms**,
with matching server IDs/routes. Scope, persisted values and complete row counts
passed; no HTTP/network/browser failures occurred; the fixture server stopped.
Artifacts: `/tmp/lab-settings-final-{browser,server}.json` and corresponding `.log`.
The final report records the settings workflow and page time origin explicitly.

**29 existing settings/browser regression tests passed**, covering explicit scopes,
global/workspace persistence and file-sidebar configuration. The Node probe passes
syntax checking; all three incompatible settings-mode combinations are rejected
before fixture startup. Test log: `/tmp/lab-settings-tests.log`.

The overall goal remains active. Settings coverage now includes these concrete
flows, but global settings writes, other sections, keyboard/dropdown timing and
larger catalogs remain unmeasured. The earlier 214.7 ms cold-open miss, heavily
traced removal overruns, prior PTY stalls and other UI/API gaps remain in the
evidence. Nothing in this checkpoint establishes a universal latency guarantee
or physical iTerm parity. No main merge, push or live-server restart is included;
the earlier merge-approval question remains pending after automatic review rejection.

## Checkpoint: index Git decorations and avoid unchanged badge mutations

The new `--git-changes N` navigation/typing fixture commits each of its disposable
workspaces and then changes N of the extra files. It disables hooks, signing and
filesystem monitors for its Git commands, uses fixture-only author details, and
never touches user repositories. The browser report records this dimension and
validates the real Git response plus both ordinary and recent-file decorations.

With 5,000 flat mixed files (`ipynb,pdf,svg,js`) and 2,500 changed files per
workspace, the existing code reproduced **17 of 600 keystrokes over 50 ms**.
The worst quiet/refreshing responses were **144.9 / 136.8 ms**, with queueing up
to 120.4 ms. All 220 API requests passed, maximum **95.6 ms**. CPU sampling
attributed **436.3 ms** across the run to `_sidebarApplyGitStatus`, including
122.2 ms in the per-row status lookup. The original algorithm scanned all Git
keys for every clean row and folder, then moved and retitled existing badges on
each application. Artifacts: `/tmp/lab-git-before-{browser,server,profile}.json`.

The production change builds per-application path indexes for added/untracked
directory inheritance, folder rollups and ignored prefixes. Lookups walk only
the row's ancestors. Exact statuses, original key-order precedence for overlapping
added/untracked directories, modified/deleted/renamed folder precedence, and all
scope guards are preserved. Existing badges only move if misplaced and only change
title when needed. Clean status results visit decorated rows, including orphan
badges/dots, so they still remove stale state without walking every pristine row
in JavaScript. No status cache duration, request schedule, template bound or
visible functionality changed.

The matched CPU-profiled run retained all 600 keys and passed every latency and
correctness check:

| Measure | Before | After |
| --- | ---: | ---: |
| Quiet typing maximum | 144.9 ms | 38.6 ms |
| Background-update typing maximum | 136.8 ms | 41.7 ms |
| Keys at or above 50 ms | 17 / 600 | 0 / 600 |
| Sampled Git decoration time, whole run | 436.3 ms | 29.7 ms |
| Sampled status lookup time, whole run | 122.2 ms | 3.0 ms |

All 233 API requests passed, maximum **94.1 ms**. The added Git assertions verified
exactly 2,500 modified paths, 5,000 correctly decorated ordinary/recent rows and
5,000 undecorated clean rows. Artifacts:
`/tmp/lab-git-after-{browser,server,profile}.json`.

A longer **unprofiled 1,200-key** check passed, including every first sample:
quiet p50/p95/max **3.3 / 23.6 / 43.2 ms**, background updates **4.0 / 25.1 /
47.9 ms**. All **411 API requests** passed, maximum **141.1 ms**. Exact echo,
focus, transport, refreshed file ordering and Git decoration checks all passed.
Artifacts: `/tmp/lab-git-long-{browser,server}.json` and corresponding `.log`.

All three runs above had no HTTP/network/browser errors, matched every browser
API ID and route to server records, and stopped their fixture servers normally.

**31 focused regression tests passed**, including a differential comparison with
the original path scans across over 28,000 adversarial/generated paths. A real
Chrome test checks every status and title, history-column placement, ignored
paths, changed/cleared state, instruction/worktree/proxy exclusions, pristine
clones, focus preservation and zero DOM mutations for repeated identical state.
It also exercises 10,000 real rows with 5,000 badges and complete clearing.
Existing sidebar rendering, cache and configuration regressions also passed.
Test log: `/tmp/lab-git-tests.log`.

The same Git-heavy fixture also passed **60 native navigation actions**: 20
workspace opens (maximum **168.3 ms**, including cold first open), 20 document
opens (**60.6 ms**) and 20 sidebar resizes (**25.0 ms**). All **344 API requests**
passed, maximum **81.1 ms**; Git status and all 10,000 fixture-row decorations
matched expectations. No HTTP/network/browser failures or correlation mismatches
occurred and the server stopped normally. Artifacts:
`/tmp/lab-git-navigation-{browser,server}.json` and corresponding `.log`.

The first 1,200-key clean-status control **failed** and is retained separately.
Quiet typing peaked at **46.1 ms**; one loaded key reached **50.4 ms** (22.7 ms
queueing, 27.7 ms handler-to-render). Its native-event timestamp validation also
failed on **654 keys**: the event epoch minus the dispatched epoch changed from
about **-0.4 to -2.9 ms** over the run. This observed mismatch needs investigation;
the run is not reclassified as passing or corrected after the fact. Exact echo,
focus, transport and updated-file checks passed. All **425 API requests** passed,
maximum **176.0 ms**, with valid server correlation and normal shutdown.
Artifacts: `/tmp/lab-git-clean-{browser,server}.json` and corresponding `.log`.

An identical unprofiled repeat passed all **1,200 keys**, with quiet/loaded maxima
**32.5 / 41.9 ms**, no correctness or timestamp errors, and a dispatched/event
epoch difference between -0.2 and 0 ms. All **420 API requests** passed, maximum
**88.3 ms**, with valid correlation and normal shutdown. This repeat does not
erase the earlier borderline miss or explain its clock mismatch. Artifacts:
`/tmp/lab-git-clean-repeat-{browser,server}.json` and corresponding `.log`.
All changed JavaScript and Python files pass syntax checks; the diff passes
whitespace checks.

The overall goal remains active. This checkpoint removes a reproduced large-Git
decoration bottleneck, but the earlier clean-control miss, timestamp drift,
PTY stalls, cold-open/API outliers and unmeasured UI flows remain open. Physical
iTerm parity is still unmeasured. No main merge, push or live-server restart is
included; the earlier merge-approval question remains pending after automatic
review rejection.

## Checkpoint: validate native input clocks and verify scrolling echo text

The earlier 654 timestamp-validation failures compared the supplied Unix epoch
directly with `performance.timeOrigin + event.timeStamp`. That assumes the
wall/monotonic clock offset remains fixed. Chromium's current `GetEventTimeTicks`
maps supplied input time using the current wall/monotonic pair, while the W3C
timing specification explicitly allows wall time to drift relative to the
monotonic timeline. Sources:
[Chromium input handler](https://chromium.googlesource.com/chromium/src/+/refs/heads/main/content/browser/devtools/protocol/input_handler.cc),
[W3C clock drift](https://www.w3.org/TR/hr-time-2/#clock-drift).
The installed browser used here reports Chrome 153.0.8010.53; the source reference
is the current upstream implementation, not a locally built browser.

The keyboard, click and resize probes now share `input_clock.mjs`. Each handler
brackets a wall-clock sample with monotonic reads. Validation maps the original
event timestamp using that current pair and retains both the raw and mapped
differences. It rejects missing/nonfinite values, brackets wider than 1 ms, and
mapped errors beyond the existing 2 ms tolerance. Latency still uses the original
event timestamp and the same 50/200 ms budgets. No latency is corrected after
measurement, and old reports lacking these clock samples remain unchanged.

Native Chrome controls confirm that a deliberate 250 ms renderer block remains
visible in input queue and render timings. Deliberately backdated/future input
timestamps of -500/+500 ms are rejected. Generated clock cases cover large
positive/negative offsets, invalid samples and uncertain brackets without
mutating durations. An initial control-test attempt omitted the required string
argument to a CDP binding and timed out; the binding and bounded waits were fixed
before successful validation. Both test logs remain in `/tmp`.

The first longer, 2,400-key terminal run exposed another probe limit: the ready
marker disappeared after **2,314 verified keys**. The terminal was 49 columns by
49 rows with a tmux status row; the 38-character marker plus those keys fill
the 48 content rows exactly. The echo trace confirms **all 2,400 bytes received
and written**, but the old matcher could not verify the remaining scrolled text.
This failed run is retained as `/tmp/lab-clock-terminal-{browser,server}.json`.
Its first 1,200-key phase passed at 36.3 ms maximum; incomplete later coverage is
not counted as a passing run. All captured clock samples validate with the new
method, but this run did not reproduce the earlier raw clock drift.

The owned typing fixture now uses reproducible varied letters instead of a
26-character repeating sequence, allowing exact alignment of a scrolled view.
Separate parse/render readers verify continuity from the initial marker, then
the complete visible suffix. They reject altered/dropped text, ambiguous
alignment, insufficient context, output ahead of input, and any unverified
characters that scrolled away. Parsed-only progress cannot authorize a gap in
rendered text. Reports include terminal dimensions, input-pattern identity and
each reader's actual scrolled-read count. Failed runs also retain clock checks.

The complete **2,400-key** follow-up with 5,000 flat mixed files, real background
file updates and owned-terminal tracing passed:

| Typing phase | p50 | p95 | Maximum |
| --- | ---: | ---: | ---: |
| Quiet, 1,200 keys | 3.2 ms | 18.5 ms | 39.7 ms |
| Background updates, 1,200 keys | 4.7 ms | 24.5 ms | 46.8 ms |

All **785 API requests** passed, maximum **140.6 ms**. All clock, exact-text,
focus, transport and updated-file checks passed. Clock brackets were at most
0.1 ms; mapped dispatch differences were -1.1 to +0.1 ms. The echo process read
and wrote all 2,400 bytes across 2,399 reads (one coalesced read), with maximum
read-to-write time 0.044 ms. For the slowest key, browser queueing took 21.1 ms
and parse-to-render another 20.7 ms; the corresponding server PTY write-to-read
took about 0.1 ms. The earlier large PTY stall did not reproduce. Browser API
IDs/routes match server records; no HTTP/network/browser errors occurred; the
fixture stopped normally. Artifacts:
`/tmp/lab-clock-scroll-{browser,server}.json` and corresponding `.log`.

The Git-heavy click/resize check retained a **253.3 ms first workspace open**,
including 28.3 ms browser queueing and an 80.8 ms file-list request. This remains
a real unprofiled budget miss. The other 59 actions passed; document maximum was
80.5 ms and resize maximum 20.1 ms. All **344 API requests** passed (maximum
80.8 ms), all 60 clock checks and all Git decorations passed, API correlation
matched and shutdown completed. Artifacts:
`/tmp/lab-clock-navigation-{browser,server}.json` and corresponding `.log`.

A short CPU/timeline diagnostic retained all eight actions: the first open took
187.5 ms, while two later workspace switches took 219.1/251.5 ms under tracing.
In the first-open window, sampling attributed **64.5 ms** to sidebar refresh,
including **50.7 ms** in template construction/mounting and **35.7 ms** in template
building. Timeline HTML parsing took 30.5 ms. Later traced switches included
substantial fresh Git-badge insertion as well as markup parsing. Those heavily
instrumented durations are not substituted for the unprofiled 253.3 ms miss.
The next production investigation is the sidebar construction portion of cold
workspace navigation. Artifacts:
`/tmp/lab-clock-cold-{browser,server,profile,trace}.json` and corresponding `.log`.

**19 diagnostic regressions passed**, including real Chrome queued keyboard,
mouse-down and click controls, exact scrolling continuity and existing ASGI/PTY
instrumentation checks. Log: `/tmp/lab-clock-final-tests.log`.

The installed iTerm2 version is **3.6.11**. Its current documentation describes
a throughput mode that lowers frame rate under heavy output and prioritizes
input processing; it does not establish a universal per-keystroke latency.
A matched local comparison remains required before claiming parity.
[iTerm2 settings documentation](https://iterm2.com/documentation-preferences-general.html).

The final **unprofiled Git-heavy 2,400-key** run retained **one real 53.3 ms miss**
in the background-update phase: 20.4 ms queueing, 18.6 ms handler-to-parse and
14.3 ms parse-to-render. Quiet maximum was 44.8 ms. Every key was verified,
including **89 parsed and 88 rendered reads after the marker scrolled away**.
All clock checks passed (brackets at most 0.1 ms, mapped differences -1.1 to
+0.1 ms); the raw clock drift did not reproduce in this run. All Git state,
exact-text, focus, transport and updated-file checks passed. All **788 API
requests** passed, maximum **131.8 ms**, with valid correlation and normal
shutdown. Artifacts: `/tmp/lab-clock-final-{browser,server}.json` and `.log`.
The passing earlier run does not erase this longer Git workload's budget miss.

This checkpoint changes diagnostics only. The overall goal remains active:
the new 53.3 ms typing and 253.3 ms cold-open misses, older outliers, unmeasured
UI flows and the matched iTerm comparison remain open. The worktree is isolated;
there is no main merge, push or live-server restart. The earlier explicit merge
approval remains pending after automatic approval review rejected the merge.

## Single-element workspace Pin controls (2026-09-22)

The next production change removes one wrapper and inline click handler from
each ordinary workspace file's Pin button. The existing shared sidebar handler
reads the button's escaped `data-pin-name`; it must not substitute the row's
file path because the old action used `f.name`. Worktree views still omit Pin
controls. Click and keyboard activation retain the original action, and the
existing row double-click behavior is unchanged. The hover rule preserves the
button's former block geometry and text baseline. Pinned shortcuts and recent
Git-history controls keep their existing behavior.

The navigation diagnostic now reports live sidebar element count and retained
pristine template size after measurement. Cache bounds remain four scopes and
60,000 elements. Neither version fits both large workspace templates at once.

The matched CPU-profiled comparison used **5,000 extra mixed files** per
workspace (`ipynb,pdf,svg,js`), flat layout, **2,500 actual modified Git paths**,
20 workspace clicks, 20 document clicks and 20 native sidebar resizes. Baseline
JavaScript and CSS came from checkpoint `31788d7`.

| Measurement | Baseline | Single-element Pin |
| --- | ---: | ---: |
| Live sidebar elements | 50,176 | 45,172 |
| Retained pristine elements | 45,173 | 40,169 |
| Retained markup characters | 5,932,275 | 5,842,203 |
| Workspace switch p50 | 114.6 ms | 102.2 ms |
| Workspace switch p95 | 142.6 ms | 132.3 ms |
| First / maximum workspace open | 149.1 ms | 150.6 ms |
| Maximum document open | 62.1 ms | 50.7 ms |
| Maximum sidebar resize | 22.1 ms | 22.6 ms |
| API requests / maximum | 341 / 72.5 ms | 343 / 103.2 ms |

The candidate removes **5,004 elements** (5,000 extra files plus four fixture
documents), about **11.1%** of pristine elements, and 90,072 markup characters.
Across the whole matched profile, inclusive sidebar-refresh samples decreased
from **1,387.0 to 1,222.3 ms**, template construction/mounting from **918.1 to
768.6 ms**, and template building from **609.6 to 524.4 ms**. These aggregate
sampled costs are not individual click durations. Git decoration costs were
roughly unchanged (262.6 to 259.6 ms).

All **60 actions** and all API requests passed in each run. Both verified
2,500 Git paths, 5,000 modified row copies and 5,000 clean row copies. Input
clocks and browser/server correlations passed, no HTTP/network/browser errors
occurred, and both owned servers stopped. Artifacts:
`/tmp/lab-pins-before-{browser,server,profile}.json` and
`/tmp/lab-pins-after-{browser,server,profile}.json`, plus corresponding logs.
The first-open time did **not** improve in this pair; the earlier unprofiled
253.3 ms miss remains unresolved.

**164 focused regressions passed:** 29 Pin/Git/file-configuration/context checks
plus 135 sidebar cache/rendering/navigation, terminal, dashboard and latency
checks. The new native Chrome test makes **96 geometry/theme comparisons**
across hover states, two widths, two zoom levels, both themes, pin state and
Git-badge presence. It also verifies mouse and Enter activation, fresh template
clones, differing pin name/file path, quoted and Unicode names, ordinary file
opening and the prior double-click behavior. The rendered screenshot was
inspected. Logs: `/tmp/lab-sidebar-pin-tests.log` and
`/tmp/lab-pins-regressions.log`; comparison JSON and screenshot under
`/tmp/lab-sidebar-pin-tests/test_sidebar_pin_controls_in_c0/`.

The final unprofiled typing check used the same Git-heavy fixture, real
background document changes and **2,400 timestamped native keys**:

| Typing phase | p50 | p95 | Maximum |
| --- | ---: | ---: | ---: |
| Quiet, 1,200 keys | 3.4 ms | 20.2 ms | 43.7 ms |
| Background updates, 1,200 keys | 5.4 ms | 26.4 ms | 45.2 ms |

All keys passed 50 ms; exact text, focus, transport and updated-file checks
passed. Independent readers verified all 2,400 characters, with 89 parsed and
87 rendered reads after the ready marker scrolled away. All input clocks
passed: sample brackets at most 0.1 ms, mapped dispatch differences -1.1 to
+0.1 ms and raw differences -0.5 to -0.1 ms. All **783 browser API requests**
passed (maximum **132.3 ms**); the server recorded **814 total requests**, maximum
**96.3 ms** through the response body. All browser IDs/routes/statuses matched
server records. Git decorations passed, no HTTP/network/browser errors occurred,
WebSocket compression remained off, and the owned server stopped. Artifacts:
`/tmp/lab-pins-typing-{browser,server}.json` and `.log`.

The final unprofiled navigation run retained all **60 actions**, all under
200 ms: workspace first **151.7 ms**, p50 **99.3 ms**, maximum **151.9 ms**;
document maximum **67.3 ms**; resize maximum **26.3 ms**. All **344 browser API
requests** passed, maximum **107.9 ms**; all **372 server requests** passed,
maximum **107.5 ms** through the response body. Input clocks, Git decorations
and request correlations passed; no HTTP/network/browser errors occurred; the
owned server stopped. Artifacts: `/tmp/lab-pins-final-{browser,server}.json`
and `.log`.

These successful checks do not erase the earlier **53.3 ms typing** and
**253.3 ms cold-open** misses or establish parity with iTerm. Broader unmeasured
UI flows and prior outliers remain open; the overall goal stays active. This
checkpoint remains in the isolated worktree, without a main merge, push or
live-server restart. Explicit merge approval remains pending after automatic
approval review rejected that action.

## Publish saved Pin state before warm refresh (2026-09-22)

The previous turn was progress: checkpoint `076735e` reduced ordinary Pin
control markup and verified navigation and typing. This turn extends coverage
to the actual Pin and Unpin interactions, which still wrote metadata and then
painted old cached pin state before the fresh file scan/metadata reconciliation.

The new `--pins` diagnostic uses timestamped native clicks, reveals hover-only
controls before timing, and measures until the shortcut, ordinary button,
cached state and rendered dashboard agree. Every action also checks metadata
persisted in the intended workspace and verifies that its ordinary file row
remains. Unpin alternates between the original row and pinned shortcut. Hover
preparation is not claimed as measured hover latency. The mode is exclusive
with typing, resize, workspace creation and settings workflows.

The initial probe accidentally selected the recent-file copy's Git-history
button. That run timed out and is retained at
`/tmp/lab-pin-action-before-{browser,server}.json` and `.log`. A small diagnostic
at `/tmp/lab-pin-action-debug-{browser,server}.json` identified the wrong control;
the ordinary-row selector now excludes `.sidebar-file-recent`. Neither failed
attempt is counted as a passing latency run.

The corrected matched comparison used **5,000 extra mixed files** per workspace
(`ipynb,pdf,svg,js`), flat layout, **2,500 actual modified Git paths**, one initial
workspace click and **20 Pin / 20 Unpin actions**, with CPU sampling enabled in
both runs. Before the change, three actions exceeded 200 ms: **299.2 ms Pin**,
**214.1 ms shortcut Unpin**, and **200.3 ms shortcut Unpin**. For the 299.2 ms
action, the metadata write completed about 24.5 ms after input; the subsequent
file scan started at 74.5 ms and took 107.6 ms, with background refresh work also
present. Waiting for fresh reconciliation was material to the visible delay.

`togglePin` now captures its workspace path, confirms successful GET and PUT
responses, and publishes the saved pin list into the latest cached payload
before the existing dashboard refresh. It preserves all other cached fields
and keeps the fresh file/metadata reconciliation. With no cache it follows the
normal cold refresh. A workspace switch during the request cannot redirect the
write to another workspace or repaint that workspace's dashboard. Failed saves
leave cached state unchanged.

| Matched CPU-profiled measurement | Baseline | Confirmed state cached |
| --- | ---: | ---: |
| Pin p50 / p95 / maximum | 121.4 / 156.7 / 299.2 ms | 102.7 / 124.4 / 131.0 ms |
| Unpin p50 / p95 / maximum | 128.6 / 200.3 / 214.1 ms | 103.3 / 114.6 / 133.4 ms |
| First workspace open | 147.2 ms | 168.2 ms |
| Actions at or above 200 ms | 3 / 41 | 0 / 41 |
| Browser API requests / maximum | 716 / 128.4 ms | 705 / 79.9 ms |
| Server requests / maximum through body | 738 / 129.5 ms | 727 / 73.9 ms |

Across the complete profiles, inclusive sidebar refresh samples decreased from
**2,914.1 to 2,384.9 ms**, template construction/mounting from **1,049.8 to
890.0 ms**, and Git decoration from **809.2 to 523.8 ms**. These are aggregate
sampled costs, not per-action durations. Both runs verified Git decorations,
all input clocks and request ID/route/status correlations. No HTTP, network or
browser errors occurred and both owned servers stopped. Artifacts:
`/tmp/lab-pin-action-baseline-{browser,server,profile}.json` and
`/tmp/lab-pin-action-after-{browser,server,profile}.json`, plus corresponding logs.

The final **unprofiled 60-cycle run** retained **121 actions** (one workspace
open, 60 Pins, 60 Unpins), all under 200 ms:

| Action | p50 | p95 | Maximum |
| --- | ---: | ---: | ---: |
| Pin | 105.3 ms | 116.5 ms | 126.8 ms |
| Unpin | 102.6 ms | 118.9 ms | 123.8 ms |

The initial workspace open took **146.6 ms**. All **2,050 browser API requests**
passed, maximum **93.2 ms**; all **2,072 server requests** passed, maximum
**90.9 ms** through the response body. All clocks, metadata persistence checks,
ordinary-row preservation checks, Git decorations and browser/server
correlations passed. No HTTP/network/browser errors occurred and the owned
server stopped. Artifacts: `/tmp/lab-pin-action-final-{browser,server}.json`
and `.log`.

**181 focused regressions passed**, including 17 new persistence/ownership
cases, native Pin geometry and actions, large sidebar cache/rendering,
navigation, Git decorations, file configuration, explorer context, dashboard,
terminal and latency checks. The new cases cover successful Pin/Unpin with
and without a cache, cache replacement during a save, workspace switches during
reads and writes, HTTP/network failures, quoted/Unicode pin names, preserving
unrelated metadata and avoiding mutation before confirmation. Log:
`/tmp/lab-pin-action-regressions.log` (90.84 s). JavaScript syntax and whitespace
checks passed; all four incompatible `--pins` workflow combinations were
rejected before fixture startup.

The measured Pin/Unpin misses are addressed in this fixture. This does not
resolve earlier cold-open/typing outliers, unmeasured interactions or the
matched iTerm comparison. The goal remains active. Work stays in the isolated
branch; no main merge, push or live-server restart occurred. The earlier main
merge approval remains pending after automatic approval review rejected it.

## Drain detached terminal output before PTY close (2026-09-23)

The previous turn was progress: `fad1247` fixed measured Pin/Unpin delays. This
turn expands coverage to terminal-tab switching, including retained views and
real eviction from the unchanged three-pane parked cache.

The new `--terminal-tabs` workload creates six uniquely named owned echo
sessions through the API and cleans up only those sessions, including partial
setup failure. Native timestamped clicks wait for the selected tab, open
connection, visible pane, focused input and exact text verified by xterm's
render callback. One real character is typed into each terminal after its first
measured visit; subsequent visits must preserve it through both cache reuse
and tmux replay. Those six setup characters are not claimed as measured typing
latency. The sequence includes first visits, the mounted tab, repeated warm
switches and cycling beyond the cache capacity. No user terminal receives input.

The initial 50-file fixture exposed a repeatable **~680 ms eviction delay**:
first-visit maximum **686.1 ms**, eviction-cycle maximum **696.6 ms**, while warm
switches stayed at **53.7 ms** maximum. All rendered text, focus and retained
characters were correct. Its sidecar also retained a **305.0 ms terminal-delete
request during cleanup**; this is a backend budget miss even though it falls
outside browser clicks. Artifacts: `/tmp/lab-terminal-tabs-smoke-{browser,server}.json`
and `.log`.

Diagnosis kept each failed budget run:

- CPU/PTY tracing (`/tmp/lab-terminal-tabs-trace-{browser,server,profile}.json`)
  showed mostly idle browser time. A representative new socket was accepted
  about 74 ms after input but produced its first terminal bytes around 644 ms.
- PTY close timing (`/tmp/lab-terminal-tabs-close-{browser,server}.json`) ruled
  out Lab's own `os.close`, which completed near zero milliseconds.
- Fork/discovery timing (`/tmp/lab-terminal-tabs-fork-{browser,server}.json`)
  found PTY creation at **0.9–5.2 ms** and session discovery at **533–541 ms**.
- Deeper discovery timing (`/tmp/lab-terminal-tabs-discovery-{browser,server}.json`)
  showed socket-routing and executable checks under 1 ms; the `has-session`
  subprocess accounted for the delay. Python stack sampling confirmed waiting
  for its output (`/tmp/lab-terminal-tabs-python-stacks.log`, plus
  `/tmp/lab-terminal-tabs-stacks-{browser,server}.json`).
- Simple immediate/drained detach controls were fast on both a separate tmux
  server and a uniquely named session in the existing server; they did not
  reproduce the browser workload (`/tmp/lab-terminal-detach-{control,default}.json`).
  A read-only check found no global client-detached hook.
- Sampling tmux during the real workload found **242 of 511 samples** in
  `server_client_lost → close` (`/tmp/lab-terminal-tabs-tmux-stack.txt`, with
  `/tmp/lab-terminal-tabs-native-stack-{browser,server}.json`). The installed
  version is 3.6a. Its source closes client descriptors in this function;
  this supports the stack interpretation but does not by itself establish
  a kernel-level cause. [tmux 3.6a client cleanup source](https://github.com/tmux/tmux/blob/3.6a/server-client.c#L398).

The production fix runs `_term_stop_pty` on a worker after both existing pumps
stop. It signals only the owned attach child, drains final output without
blocking reads until a **100 ms deadline**, then closes the master and performs
the existing nonblocking reap. The deadline bounds the drain loop, not every
possible operating-system syscall delay. It sends no input and leaves the tmux
session alive. The worker keeps cleanup off the shared event loop. Cache limits,
authorization, socket affinity and active terminal byte handling are unchanged.

The matched 50-file follow-up removed the repeatable stall:

| Maximum action duration | Original cleanup | Drained cleanup |
| --- | ---: | ---: |
| First terminal visits | 686.1 ms | 154.5 ms |
| Mounted tab | 50.8 ms | 52.3 ms |
| Warm switches | 53.7 ms | 55.1 ms |
| Eviction cycle | 696.6 ms | 151.5 ms |

All 20 follow-up actions passed. Session-discovery maximum fell to **10.5 ms**;
all server requests passed, maximum **59.6 ms**. Artifacts:
`/tmp/lab-terminal-tabs-drain-{browser,server}.json` and `.log`.

The final unprofiled large workload used **5,000 mixed files**, flat layout,
**2,500 actual modified Git paths**, and **128 native actions**:

| Action | Samples | p50 | p95 | Maximum |
| --- | ---: | ---: | ---: | ---: |
| First terminal visits | 6 | 150.4 ms | 155.9 ms | 155.9 ms |
| Mounted tab | 1 | 54.4 ms | 54.4 ms | 54.4 ms |
| Warm switches | 60 | 82.9 ms | 89.3 ms | 96.6 ms |
| Eviction cycle | 60 | 147.4 ms | 156.9 ms | 166.7 ms |

The initial workspace open took **156.2 ms**. Every action passed 200 ms. All
**109 browser API requests** passed, maximum **102.1 ms**; all **148 server
requests** passed, maximum **101.5 ms** through the response body, including
fixture setup and cleanup. Artifacts:
`/tmp/lab-terminal-tabs-large-{browser,server}.json` and `.log`.

Actual pre-click cache states were **65 cold, 60 warm and 2 mounted** (plus the
workspace click). All 128 input clocks passed the existing strict validation,
and every browser API request matched its sidecar request ID and route. Git
verification found exactly 2,500 modified paths. There were no browser, API or
transport failures; the owned server stopped. The final state retained exactly
three parked panes plus the active pane with the expected rendered text.

The added `--typing-detaches` workload passively attaches another owned echo
terminal and detaches after receiving its marker, once per loaded refresh
interval. It sends no terminal input. The first attempt failed during setup:
automatic initial restore selected the second terminal before the explicit
typing selection. No measured key or foreground WebSocket frame was sent.
The fixture now waits for that initial restore before selecting the target.
Both owned sessions and the server were cleaned up; the failed artifact remains
`/tmp/lab-terminal-tabs-typing-{browser,server}.json` and `.log`.

The corrected run measured **2,400 keys** at the unchanged 25 ms input cadence,
with the same 5,000-file/2,500-Git-change fixture:

| Phase | Keys | p50 | p95 | Maximum |
| --- | ---: | ---: | ---: | ---: |
| Normal polling | 1,200 | 3.4 ms | 21.3 ms | 48.8 ms |
| File updates, refreshes and detach cycles | 1,200 | 5.6 ms | 26.8 ms | 41.5 ms |

Every key passed 50 ms, including the first key in each phase. The loaded phase
completed **60 detach cycles, 60 refreshes and 60 real file updates**. Independent
parse/render readers verified all 2,400 characters, including text after the
initial marker scrolled away; the echo sidecar recorded 2,400 bytes read and
written. All input clocks passed, foreground WebSocket compression stayed off,
and no typing/transport/browser/API errors were reported. Every one of the
**849 browser API requests** matched a sidecar ID and route, maximum **92.3 ms**;
all **882 server requests** stayed below 200 ms, maximum **90.5 ms**. The sidecar
also records the browser's unrelated `/favicon.ico` 404. Both fixture terminals
were deleted and the owned server stopped. Artifacts:
`/tmp/lab-terminal-tabs-typing-ready-{browser,server}.json` and `.log`.

These are external CDP input-to-xterm-render measurements with PTY metadata
tracing enabled, not physical keyboard-to-display or matched iTerm results.
The final tab-switch run had no CPU or PTY profiling enabled.

Validation covered **287 affected terminal and diagnostic regressions**. The
first invocation passed 286 and failed one native Chrome lifecycle test because
the sandbox prevented Chrome from starting; that test passed when rerun with
the required access. Logs: `/tmp/lab-terminal-tabs-regressions.log` and
`/tmp/lab-terminal-tabs-chrome-regression.log`. New tests cover bounded drain
completion on EOF, EIO, silence, continuous output, missing children and invalid
descriptors; event-loop responsiveness during worker cleanup; fd reuse during
timing; exact rendered tab contents; and fixture ownership/partial-failure
cleanup. Nine incompatible or incomplete CLI combinations were rejected before
startup. JavaScript syntax, Python compilation and whitespace checks passed.

This fixes the repeatable terminal eviction stall in the measured fixture.
Earlier cold-open and typing outliers, unmeasured UI/backend paths and the
matched iTerm comparison remain open; later passing runs do not erase them.
The goal remains active. Work stays in the isolated branch; no main merge,
push or live-server restart occurred. The earlier main merge approval remains
pending after automatic approval review rejected it.

## Measure Command+K and avoid unused logging layout (2026-09-23)

The previous turn made progress in checkpoint `cbb3042`, removing the measured
terminal-detach stall. This turn extends native interaction coverage to the
Command+K file picker and removes an unnecessary synchronous layout read from
shared action logging.

The new `--quick-files` mode uses the existing isolated Lab lifespan and fresh
Chrome profile. Each repetition opens search with native Command+K, types all
seven characters of `review-`, selects down/up, opens the selected document
with Enter, then reopens and closes with Escape. Measurements include browser
input queueing and wait for a paint opportunity after the expected state.
Checks require the loaded dialog, focused input, captured workspace/root,
correct visible paths and selection, and the expected rendered document.
The complete result order is checked independently against file metadata and
the configured preferred formats, including the first-100 limit. All generated
fixture files must be present. No fetch, polling or production picker behavior
is replaced. The workflow rejects nonfixture roots and incompatible modes.

The first unprofiled 5,000-file, 2,500-modified-Git-path run retained two misses:
**231.3 ms** for the first workspace click and **463.7 ms** for the first picker
open. The latter's file-list request took only **33.1 ms**. Other picker actions
passed, and all backend requests passed. All 27 input clocks and request-ID
correlations were valid. Artifacts: `/tmp/lab-quick-files-baseline-{browser,server}.json`
and `.log`. These samples remain in the record.

The matched four-repetition browser profiles showed `_describeElement` in
`error-report.js` spending **216.5 ms** across named input-change events in the
baseline. Its unconditional `innerText` read forced style recalculation while
dialogs were being removed, although `name`, `aria-label` or `title` already
supplied the logged description. A trace captured a **67.6 ms** synchronous
style/layout update and about 29,000 elements styled during one such change.

The production change reads rendered text only when no existing label wins.
Attribute precedence, logged action/id/href metadata, batching and uploads stay
the same; unnamed controls retain their prior innerText/textContent fallback,
whitespace normalization and 80-character truncation. Regression tests make
text access throw for each named-control case and check fallback output.

The candidate profile had no sampled `_describeElement` cost. Aggregate
`Document::UpdateStyleAndLayout` synchronous duration fell from **562.4 ms** to
**342.6 ms**, maximum **67.6 ms → 7.1 ms**. Total style-update time stayed similar
(**1,071.5 ms → 1,108.6 ms**); modal lifecycle still requires style work. These
small profiled runs establish removal of the unnecessary forced read, not a
uniform reduction in total rendering time or the cause of the entire 463.7 ms
outlier. Baseline/candidate picker-open maxima were **177.7/121.7 ms**, document
open maxima **120.6/102.9 ms**, and Escape maxima **65.3/65.0 ms**. The candidate
also retained a **221.1 ms first workspace click**.

Artifacts: `/tmp/lab-quick-files-traced-{browser,server}.json`,
`/tmp/lab-quick-files-baseline-{trace,profile}.json`,
`/tmp/lab-quick-files-after-{browser,server,trace,profile}.json` and logs.

The first 20-repetition unprofiled large run completed **261 native actions**:

| Action | Samples | p50 | p95 | Maximum |
| --- | ---: | ---: | ---: | ---: |
| Command+K open | 40 | 86.6 ms | 105.5 ms | 119.6 ms |
| Filter character | 140 | 27.3 ms | 35.1 ms | 43.0 ms |
| Arrow selection | 40 | 26.5 ms | 33.9 ms | 35.8 ms |
| Enter document open | 20 | 66.4 ms | 72.4 ms | 92.7 ms |
| Escape close | 20 | 43.0 ms | 44.1 ms | 44.2 ms |

The initial workspace click took **146.1 ms**. Every action passed 200 ms. All
**163 browser API requests** passed, maximum **50.5 ms**; all **192 sidecar
requests** passed, maximum **49.6 ms**. Every input clock was valid, every
browser API request matched the sidecar ID/route, Git verified all 2,500
modified paths, and no browser/API/network failures were recorded. The owned
server stopped. Artifacts: `/tmp/lab-quick-files-final-{browser,server}.json`
and `.log`.

The affected logging, quick-file, navigation and input-clock suite covered
**111 passing tests**. Initially 110 passed and the native clock test could
not launch Chrome inside the sandbox; that test passed with the required
access. Logs: `/tmp/lab-quick-files-regressions.log` and
`/tmp/lab-quick-files-native-clock.log`. The first targeted invocation also
caught two incorrectly escaped newline literals in the new fallback test
data; after correcting the data, all 35 targeted tests passed. Six conflicting
`--quick-files` combinations fail before fixture startup.

The shared-logging typing check used the same large Git-heavy fixture, normal
polling, 60 fresh sidebar refreshes and 60 real file updates. All **2,400 keys**
passed 50 ms: normal p50/p95/max **3.4/22.1/42.6 ms**, loaded
**2.8/24.6/43.1 ms**. Both independent readers verified all characters through
scrolling, all clocks passed, and no browser, transport or API failures were
recorded. All **795 browser API requests** passed (maximum **130.4 ms**), as did
all **826 server requests** (maximum **89.3 ms**). Every API request correlated
by sidecar ID/route; the echo session was deleted and the owned server stopped.
Artifacts: `/tmp/lab-quick-files-typing-{browser,server}.json` and `.log`.

The final verification strengthened the picker checks to require every
generated path individually (rather than only the generated-file count) and
the opened document's exact root. Its **261 native actions** all passed:

| Action | Samples | p50 | p95 | Maximum |
| --- | ---: | ---: | ---: | ---: |
| Command+K open | 40 | 87.6 ms | 118.1 ms | 151.7 ms |
| Filter character | 140 | 26.8 ms | 33.8 ms | 38.6 ms |
| Arrow selection | 40 | 27.3 ms | 35.8 ms | 38.3 ms |
| Enter document open | 20 | 66.4 ms | 72.8 ms | 100.6 ms |
| Escape close | 20 | 41.7 ms | 44.7 ms | 46.9 ms |

Workspace open was **148.2 ms**. All **166 browser API requests** passed,
maximum **88.6 ms**, and all **195 server requests** passed, maximum **88.0 ms**.
Clocks, complete expected results, Git state, ID/route correlation and cleanup
all passed, with no recorded errors. The two diagnostic unit tests passed
again after strengthening these checks; JavaScript syntax, Python compilation
and whitespace checks passed. Artifacts:
`/tmp/lab-quick-files-verified-{browser,server}.json` and `.log`.

The goal remains active. This checkpoint preserves logging behavior and removes
its unused forced text read; it does not establish that all cold opens meet
200 ms. The new **463.7 ms picker**, **231.3/221.1 ms workspace** samples and
older outliers remain unresolved, as do broader unmeasured actions and the
matched iTerm comparison. No main merge, push or live-server restart occurred.
The earlier merge approval remains pending after automatic approval review
rejected that action.

## Share sidebar file identity across actions (2026-09-23)

The previous turn made progress in `5b9d0eb`, removing unused rendered-text
reads from action logging and adding native Command+K coverage. This turn
revisited retained cold-opening misses before changing another part of the
sidebar's construction cost.

Reanalysis of `/tmp/lab-quick-files-after-{browser,server,trace,profile}.json`
showed the **221.1 ms** first workspace click had only **2.2 ms input queueing**,
a **95.5 ms** server file-list response, and substantial sidebar construction.
CPU samples attributed about **54.1 ms** to `_refreshWorkspaceSidebar`, including
**29.9 ms** in template construction and **7.5 ms** in cloning. This does not
explain the separate 463.7 ms picker miss. The earlier unprofiled 231.3 ms
workspace sample had **58.7 ms queueing**, so the retained misses do not all
have the same measured shape.

A new trace with handler/file/session timings passed: workspace **152.2 ms**,
picker maximum **156.3 ms**. Its first workspace file-list response took
**35.6 ms**, with **28.9 ms** in guarded scanning; one later file-list response
took **70.8 ms**, including **65.5 ms** in the guard. No stable source of the
scan-time variability was established. Artifacts:
`/tmp/lab-cold-open-{browser,server,trace,profile}.json` and `.log`.

The production change removes duplicate entry-kind/path attributes from normal
workspace, self/vault and Recently updated file rows. Opening, context menus,
file drags, terminal-link drops and linked-file reveal now share the rows'
existing `data-open-file`, `data-filepath` and explicit `data-entry-root`.
Repository trees, folders, pinned shortcuts and instruction rows retain their
explicit entry metadata. Explicit paths retain precedence, including rejecting
an explicitly empty legacy path. Virtual rows remain excluded. This changes no
visible element, geometry, cache limit, file scan, polling interval or action.

Four sequential unprofiled runs used the same 5,000 mixed files, flat layout,
2,500 real modified Git paths and eight workspace/eight document clicks each.
Only the app source changed for the baseline (`5b9d0eb`), in baseline/candidate/
candidate/baseline order:

| Run | First workspace | Workspace p50 | Workspace maximum | Document maximum |
| --- | ---: | ---: | ---: | ---: |
| Baseline 1 | 150.4 ms | 100.4 ms | 150.4 ms | 65.1 ms |
| Candidate 1 | 135.3 ms | 101.8 ms | 135.3 ms | 68.3 ms |
| Candidate 2 | 161.6 ms | 110.8 ms | 161.6 ms | 64.3 ms |
| Baseline 2 | 144.8 ms | 104.0 ms | 144.8 ms | 67.1 ms |

All 64 actions passed, but these end-to-end results are mixed and do not
establish a consistent cold-open improvement. All API requests, clock checks,
request-ID/route correlations, Git checks and cleanup passed. Artifacts:
`/tmp/lab-sidebar-identity-{before-1,after-1,after-2,before-2}-{browser,server}.json`,
their logs, and `/tmp/lab-sidebar-identity-comparison.json`.

The structural reduction is deterministic: **10,008 rows** lose two redundant
attributes; retained markup falls from **5,842,203 to 5,209,255 characters**
(**632,948 fewer, 10.8%**). Live elements remain **45,172**, pristine template
elements **40,169**, and the four-scope/60,000-element retention limits remain
unchanged.

An optional `LAB_PERF_FILE_IDENTITY_PROFILE=<output.json>` diagnostic isolates
the affected construction step after native actions finish. It reconstructs
the previous repeated attributes from the exact same compact markup, verifies
equal DOM after removing just those attributes, and alternates both orders for
12 samples per form. It builds and clones detached templates without mounting
them. This is a component measurement after page load, not a cold-open or
keyboard-latency measurement:

| Component | Repeated attributes median | Shared identity median |
| --- | ---: | ---: |
| Template construction | 23.0 ms | 20.9 ms |
| Clone | 4.8 ms | 4.6 ms |
| Combined | 28.1 ms | 25.6 ms |

Combined maxima were **39.0/34.1 ms**. The modest **2.5 ms median construction
and clone reduction** supports retaining the smaller representation; it does
not resolve the earlier cold misses. Artifacts:
`/tmp/lab-sidebar-identity-components.json`,
`/tmp/lab-sidebar-identity-component-{browser,server}.json` and `.log`.

The final unprofiled native navigation/resize check passed all **60 actions**:

| Action | Samples | p50 | p95 | Maximum |
| --- | ---: | ---: | ---: | ---: |
| Workspace | 20 | 98.6 ms | 131.9 ms | 134.7 ms |
| Document | 20 | 33.7 ms | 51.0 ms | 54.5 ms |
| Sidebar resize | 20 | 13.1 ms | 20.7 ms | 27.9 ms |

All **343 browser API requests** passed, maximum **72.1 ms**, and all **372
server requests** passed, maximum **71.5 ms**. All clocks, ID/route correlations,
2,500 Git changes and owned-server cleanup passed without browser/API/network
errors. Artifacts: `/tmp/lab-sidebar-identity-final-{browser,server}.json` and `.log`.

Validation covers **191 affected regressions** across explorer, clipboard,
terminal links, file configuration, navigation, Pin persistence, Git decoration,
pristine caching and real-Chrome rendering. The native Git test initially could
not start Chrome inside the sandbox and passed with the required access. New
checks verify the shared identity on quoted/Unicode rows, captured foreign
roots, legacy metadata precedence, virtual-row exclusion, native secondary
clicks, drag payloads, terminal-link drops and preferred-row reveal.

The first expanded browser check incorrectly expected a constructed
`DataTransfer` to accept `effectAllowed='copy'`; it retained `none` even though
the exact path payload was correct. Copy mode is now verified on a trusted
native dragstart, which passes, and that test drag is then cancelled. One
subsequent existing pixel check differed at two boundary pixels after the new
drag step. Moving the pointer away before independent paint checks yielded
passing flat/nested runs with the original tolerance. Logs retain all attempts:
`/tmp/lab-sidebar-identity-{regressions,browser-tests,drag-diagnostic,native-tests,rendering-final}.log`.
After preserving explicitly empty legacy paths, all **88 targeted explorer and
terminal tests** passed again (`/tmp/lab-sidebar-identity-explicit-empty.log`).

The unprofiled typing check retained all **2,400 keys**, with 60 real file
updates and 61 loaded-phase refreshes in the same 5,000-file/Git-heavy fixture:

| Phase | Keys | p50 | p95 | Maximum |
| --- | ---: | ---: | ---: | ---: |
| Normal polling | 1,200 | 2.7 ms | 21.1 ms | 36.4 ms |
| File updates and sidebar refreshes | 1,200 | 2.5 ms | 23.8 ms | 40.7 ms |

Every key passed 50 ms. Independent parse/render readers verified all text,
including after the marker scrolled away; every clock passed. All **835 browser
API requests** passed, maximum **85.1 ms**, and all **866 server requests**
passed, maximum **84.6 ms**. API ID/route correlation, 2,500 Git changes, terminal
text, transport settings and cleanup passed with no reported typing/browser/API
errors. Artifacts: `/tmp/lab-sidebar-identity-typing-{browser,server}.json`
and `.log`. JavaScript syntax, Python compilation and whitespace checks passed.

This checkpoint reduces repeated metadata and measured construction work. The
goal remains active: mixed whole-action comparisons and later passing runs do
not resolve earlier workspace/picker/typing outliers, broader unmeasured UI and
backend paths or the matched iTerm comparison. No main merge, push or live-server
restart occurred; the earlier merge approval remains pending after automatic
approval review rejected it.

## Measure document saves and cancellation across workspaces (2026-09-23)

This checkpoint adds measurement coverage; it changes no production behavior.
The original goal remains incomplete. Earlier cold navigation and typing misses
remain evidence, and the locally matched iTerm comparison is still unavailable.

The new `--document-edit` workflow alternates between Alpha and Beta, which each
contain `docs/review-1.md` and `docs/review-2.md`. Native clicks open the document,
open its editor, save a revision, reopen it, cancel another revision, and close
the modal. First workspace visits require the dashboard; subsequent visits
require the previously saved document to be restored. Editor readiness includes
the exact source, textarea focus, the loaded two-file sibling list and disabled
sibling buttons. Save, Cancel and Close require all expected headings and
paragraphs in both modal and inline views, unchanged document/workspace identity,
and restored file navigation. Saved text exercises Unicode, literal angle
brackets inside code, ampersands and quotes.

Every Save, Cancel and Close also compares all four files byte-for-byte with
independent expected contents, outside the measured click. This checks both
same-named files in the other workspace and each unedited sibling. Text insertion
prepares the Save/Cancel action; it is not a measurement of editor typing. The
existing external click timestamps, strict input-clock checks, paint opportunity,
normal polling, complete request reporting and 200 ms budget remain unchanged.
`--document-sections` changes fixture Markdown size; its default stays at 30.

Evidence, including failed runs:

- The first 30-section smoke run completed all **14 actions**, maximum **72.4
  ms**. Its browser request to `/api/log/client` took **222.6 ms**, so the run
  failed the request budget. The corresponding server request, ID 65, took
  **8.51 ms** after ASGI entry and began about **214.2 ms** after the browser's
  resource start. This locates most delay before application entry; it does not
  establish whether the source was browser scheduling, transport, or server
  admission. All 79 browser requests correlated to the 108 server requests;
  server maximum was 59.77 ms. The owned server stopped.
- An initial 300-section, 5,000-file run completed 14 actions (maximum 172.3 ms)
  before its third workspace click timed out. The fixture incorrectly required
  a dashboard when the application restored the last document. Only the probe
  expectation was corrected. The failed run and its prior timings are retained;
  its owned server stopped. This is not a production regression or a passing
  28-action run.
- The final unprofiled run used **300 sections per document, 5,000 mixed
  ipynb/pdf/svg/js files per workspace, and 2,500 actual Git changes**. All
  **140 actions** passed. All **780 browser requests** were below 200 ms
  (maximum **75.1 ms**), as were all **809 server requests** (maximum **74.785
  ms**). Every browser request correlated by server ID and route. All native
  clocks, Git response/decorations, exact content checks and browser/error checks
  passed. The 60 persistence checkpoints compared **240 files**, with 81,253
  bytes across the four files at the final checkpoint. The server stopped.

| Final action | Samples | Median | p95 | Maximum |
| --- | ---: | ---: | ---: | ---: |
| First workspace visit | 2 | 167.0 ms | 167.0 ms | 167.0 ms |
| Open document | 20 | 32.1 ms | 49.3 ms | 64.7 ms |
| Open editor | 20 | 49.7 ms | 52.8 ms | 53.3 ms |
| Save and update both views | 20 | 66.9 ms | 80.5 ms | 83.8 ms |
| Reopen saved editor | 20 | 51.4 ms | 54.6 ms | 59.2 ms |
| Cancel and retain saved content | 20 | 35.0 ms | 41.7 ms | 44.6 ms |
| Close modal | 20 | 35.9 ms | 39.1 ms | 41.4 ms |
| Restore visited workspace/document | 18 | 108.2 ms | 123.0 ms | 123.0 ms |

These results cover the stated fixture. They do not erase the first logging
request miss, prove behavior for arbitrarily large documents, or cover editor
keystrokes, concurrent conflicting edits, comments, artifact links, notebook
execution, every other UI flow, or the unmerged production lifecycle.

Validation covers disposable-scope rejection before reads/input, immutable
per-step expectations, exact Unicode contents, detection of unintended writes
to the other workspace or sibling, cancelled drafts, incompatible workflow
flags, and invalid document size. **15 focused probe/clock/echo checks passed**
in the final combined invocation. After tightening the disk verifier to compare
raw UTF-8 bytes directly, all **10 document-probe checks passed again**. The
earlier sandbox invocation passed 14 checks but
could not start Chrome for the native-clock test; that test then passed with
access to its owned Chrome process. No production test result is inferred from
this diagnostic-only change.

Artifacts:

- `/tmp/lab-document-edit-{smoke,large,final}-{browser,server}.json`, plus matching
  `.log` files; `large` is the retained incorrect-expectation run.
- `/tmp/lab-document-edit-summary.json` contains complete final per-action
  statistics, request correlation counts and retained smoke request miss.
- `/tmp/lab-document-edit-{probe-tests,native-clock,tests-final,bytes-tests}.log`.

Example (from a checkout with its Python environment):

```sh
core/.venv/bin/python scripts/perf/lab_navigation_latency.py \
  --document-edit --document-sections 300 --samples 20 \
  --extra-files 5000 --extra-file-types ipynb,pdf,svg,js \
  --extra-file-layout flat --git-changes 2500 \
  --server-timings /tmp/lab-document-edit-server.json
```

### Local iTerm comparison remains unresolved

The installed scripting API reported iTerm2 **3.6.11**. Its bundled
`/Applications/iTerm.app/Contents/Resources/iTerm2.sdef` exposes session IDs,
window creation, input text and visible screen contents. The official
[screen API documentation](https://iterm2.com/python-api/screen.html) describes
screen-content access and change notifications; neither this API nor the
[rendering preferences documentation](https://iterm2.com/documentation-preferences-general.html)
provides an end-to-end keyboard/display measurement. Scripted text injection
and buffer polling must not be labeled native keyboard-to-render latency.

Read-only macOS checks for the owned test process returned `AXTrusted=false`,
`PostEvent=false` and `ScreenCapture=false`; no permissions or preferences were
changed. A System Events capability check did not return and was stopped. A
separate iTerm smoke call requested an owned window running only `/bin/sleep 2`,
but did not return its window/session ownership result before being stopped.
No `/bin/sleep 2` process remained at inspection; window creation/closure was
not verified. The computer-use connector then explicitly refused iTerm access
for safety reasons. No alternative UI access was attempted after that refusal.
Both owned automation processes were stopped and their execution sessions
confirmed exit 143. **No local iTerm latency number was obtained**, and no
physical keyboard/display parity is claimed.

Local merge remains pending after the earlier automatic approval-review
rejection. The independently modified main checkout and live Lab server were
not changed.

## Publish confirmed document saves before the inline refresh (2026-09-23)

Save now publishes the successfully submitted content into its captured document
cache entry before refreshing the inline pane. Previously the modal rendered
saved text, the inline pane rendered old cached text, and then a fresh response
rendered the saved text again. With unchanged server data, the final behavior is
two renders instead of three. Content, comments and artifact reads still run;
changed fresh data still causes a reconciliation render. Only an existing cache
object that has not been replaced since submission is updated, preserving its
other fields and avoiding incomplete/newer cache overwrites.

The write captures its workspace, document root, file, source and textarea before
awaiting the response. A response can update the original confirmed cache but
cannot repaint another workspace/root/file, close a newer editor, or discard a
draft typed while the write was pending. Rejected and failed writes leave the
cache and editor unchanged. This applies to ordinary document files and explicit
worktree roots without changing the file endpoint or authorization behavior.

### Reproducible Save improvement

The unprofiled comparison used 1,500 Markdown sections per document (about
101,000 characters), 5,000 mixed ipynb/pdf/svg/js files per workspace, and 2,500
actual Git changes. It alternated baseline/candidate/candidate/baseline; the
baseline app script came from `f5a8c3c`. Each run made 28 measured clicks and eight
small native IME additions, checking all rendered headings/paragraphs and all
four saved/cancelled files. The input mode is explicitly `append`; full-content
replacement is a separate failing workload described below.

| Run | Save samples | Save median | Save maximum | Other click misses |
| --- | ---: | ---: | ---: | --- |
| Baseline 1 | 4 | 225.35 ms | 240.3 ms | Workspace 287.4 ms |
| Candidate 1 | 4 | 160.65 ms | 170.6 ms | Workspace 274.6 ms |
| Candidate 2 | 4 | 150.30 ms | 152.3 ms | None |
| Baseline 2 | 4 | 224.45 ms | 244.0 ms | None |

All eight baseline Saves exceeded 200 ms; all eight candidate Saves passed.
Combined median Save latency fell from 225.35 to 152.6 ms (about 32%). The
baseline/candidate runs retained their first clicks and all misses. Browser
request maxima were respectively 135.7, 99.0, 86.1 and 56.6 ms; server maxima were
134.45, 96.58, 83.45 and 55.38 ms. Each browser request correlated by server ID
and route. All clocks, content checks, Git checks and owned-server cleanup
passed. These Save results do not claim that the separate workspace misses were
fixed.

A CPU/full-trace run of the unchanged Save path produced 697.8 and 754.3 ms Save
samples. Those timings are retained and labeled **profiled**: collecting the
large trace adds substantial overhead. They are not substituted for the
unprofiled comparison. The regression test executes the actual Save and render
functions with deferred responses and verifies the exact render sequence plus
all three fresh reads.

The final unprofiled candidate run completed 140 clicks and 40 small IME text
additions. **All 20 Saves passed**, median 149.3 ms, p95 155.5 ms, maximum
**161.9 ms**. Document opens maxed at 108.7 ms, editor opens at 70.6 ms, reopens
at 78.1 ms, Cancel at 74.5 ms and modal Close at 40.9 ms. However, the **overall
run failed** and remains evidence:

- First workspace visits took **201.3 and 200.3 ms**.
- Two restored workspace/document actions took **224.0 and 218.3 ms**.
- Two small IME setup additions took **227.15 and 253.28 ms** through command
  acknowledgement. Their rendering/display latency is not established by that
  measurement.

All 792 browser API requests stayed under 200 ms (maximum **89.0 ms**), as did
all 821 server requests (maximum **86.94 ms**). All IDs/routes correlated, all
140 input clocks passed, and no browser/network/Git errors occurred. Sixty
persistence checkpoints compared 240 files byte-for-byte, reaching 404,853 bytes
across the four documents. The owned server stopped. The earlier **222.6 ms
logging request** was not reproduced or resolved; do not attribute its earlier
pre-ASGI delay to this Save fix.

### Large native text replacement remains a separate failure

The first 1,500-section full-replacement run timed out waiting 15 seconds for
`Input.insertText`, after successful workspace/document/editor clicks of
196.7/109.0/68.1 ms. A second run reproduced the timeout while collecting CPU and
browser traces. Failed runs now save requested diagnostics before closing the
owned Chrome process; the repeated failure saved both files successfully and
its owned server stopped. The trace contains thousands of textarea selection,
editing and layout operations; CPU sampling attributed most time to native or
otherwise unattributed `(program)` work, not a measured Lab JavaScript handler.

An independent blank-page textarea control on **Chrome 153.0.8010.53** returned
exact text for all three cases:

| Source and replacement | CDP acknowledgement | Observation after paint opportunity | Trusted input events |
| --- | ---: | ---: | ---: |
| 300 sections, 20,022 characters | 434.0 ms | 448.4 ms | 1,804 |
| 1,500 sections, 100,922 characters | 12,586.1 ms | 12,617.5 ms | 9,004 |
| Same source flattened, two revision line breaks retained | 10.3 ms | 13.5 ms | 4 |

This is a single sample per control, not a latency distribution. It shows the
multiline problem also occurs without Lab; it does not prove equal cost in the
full application. Current [Chromium's `InputHandler::InsertText` implementation](https://chromium.googlesource.com/chromium/src/+/master/content/browser/devtools/protocol/input_handler.cc)
routes this command through `ImeCommitText`. This command is not a clipboard
paste or a physical typing/display measurement. No clipboard contents or
browser preferences were changed, and no input handling was replaced in the
production app.

The default document workload still uses full replacement. The new explicit
`--document-edit-input append` mode adds only each revision's suffix to the same
large source; both modes verify identical saved contents and cancelled drafts.
Every text setup now records its external acknowledgement duration, size, mode
and completion. A timeout or duration at/above 200 ms fails the run even if the
subsequent clicks pass. Thus the older 300-section checkpoint's passing click
results do not establish fast whole-document IME replacement. Native clipboard
paste and editor keystroke-to-render coverage remain missing.

### Verification and artifacts

**82 focused checks passed**: confirmed cache publication, fresh content/comments/
artifacts, absent or independently replaced cache entries, failed writes,
workspace/root/file switches, explicit worktree roots, changed drafts, closed or
reopened editors, append/replacement equivalence, workspace navigation and
rename, workspace-file routes, Markdown routes, document terminals, quick-file
behavior and native input clocks. JavaScript syntax, Python compilation and
`git diff --check` passed. The broad historical suite's two unrelated main
failures remain as documented earlier; it was not rerun or claimed green.

- `/tmp/lab-document-1500-append-{before,after,after-2,before-2}-{browser,server}.json`
  and matching `.log` files; `/tmp/lab-document-save-abba.json` summarizes them.
- `/tmp/lab-document-save-final-{browser,server,summary}.json`,
  `/tmp/lab-document-save-final.log`, and `/tmp/lab-document-save-regressions.log`.
- `/tmp/lab-document-edit-1500-before-{browser,server}.json` is the original
  full-replacement failure.
- `/tmp/lab-document-paste-1500-{browser,server,trace,profile}.json` is its traced
  reproduction; `/tmp/lab-document-paste-trace-summary.txt` summarizes the trace.
- `/tmp/lab-document-render-1500-before-{browser,server,trace,profile}.json`
  contains the separately profiled Save workload.
- `/tmp/lab-editor-input-control.mjs` and
  `/tmp/lab-editor-input-control{,-summary}.json` contain the blank-page controls.

Repeat the larger Save workload with:

```sh
core/.venv/bin/python scripts/perf/lab_navigation_latency.py \
  --document-edit --document-edit-input append --document-sections 1500 \
  --samples 20 --extra-files 5000 --extra-file-types ipynb,pdf,svg,js \
  --extra-file-layout flat --git-changes 2500 \
  --server-timings /tmp/lab-document-save-server.json
```

The full goal remains active. Large-document input and workspace switching
still exceed the budget, earlier misses remain unresolved, iTerm parity is
unverified, and integrated production verification is pending. No main merge,
push or live-server restart occurred; local merge still awaits the earlier
approval after automatic review rejected it.

## Skip disclosure searches in ordinary Markdown (2026-09-23)

**Checkpoint:** avoid repeatedly scanning document suffixes for disclosure tags
when the source cannot contain one. This change is in the shared Markdown
renderer, so documents, notebook Markdown and Assistant content keep the same
sanitization, highlighting and code-copy pipeline. It does not change any
backend endpoint, cache limit, polling interval or interaction readiness check.

### What the traces established

Two initial six-repetition large-document runs recorded calls to sidebar and
dashboard refreshes, file reads, document opens and document renders. The first
had a **203.7 ms warm restore without overlapping dashboard refreshes**; the
second passed all 42 clicks. In the latter, cached sidebar work took roughly
63–76 ms and synchronous document rendering roughly 36–43 ms during warm
restores. The document render started after sidebar work. Duplicate refreshes
therefore cannot explain every observed workspace-switch miss.

The Markdown disclosure extension calls a regex from Marked's `start` hook.
Marked invokes that hook on the remaining source for each paragraph, producing
repeated scans even when the entire document has no disclosure. A parser-only
Node experiment using vendored Marked and identical generated source found
roughly 32 ms versus 8 ms at 1,500 sections, and 300 ms versus 25 ms at 5,000
sections, with equal HTML. These are component measurements, not UI latency.

`LabMarkdown.render` now lazily reuses a base Marked parser for sources without
possible `<details>`, `<summary>` or closing tags. Detection is deliberately
conservative: mixed case, code samples, comments and malformed possible tags
keep the existing extension. Custom hooks, tokenizers and extensions also keep
it, because they can introduce tags after detection. Non-string error behavior
and per-call image renderers are preserved. Both parsers use the existing DOM
sanitizer and postprocessing; no source content or rendered DOM is cached.

### Before/candidate comparisons

Each full comparison used six edit repetitions (42 native clicks), 1,500
sections per document, 5,000 mixed flat files per workspace and 2,500 actual Git
changes. Native input clocks, all first samples, normal polling, exact saved
bytes and complete modal/inline document checks remained enabled. The optional
call tracer was enabled equally on both revisions; no CPU profiler was used.
Only `markdown-content.js` was swapped for the baseline revision `40253dc`.

| Run order | Document-render median | Save median / maximum | Warm-restore median / maximum | Other failures |
| --- | ---: | ---: | ---: | --- |
| Baseline | 41.3 ms | 171.7 / 177.8 ms | 168.5 / 171.9 ms | Cold switches 251.4, 269.3 ms; text setup 205.1 ms |
| Candidate | 23.8 ms | 131.3 / 133.6 ms | 149.3 / 167.7 ms | Cold switch 200.8 ms; text setups 201.5, 203.5 ms |
| Candidate repeat | 21.3 ms | 113.9 / 121.0 ms | 151.7 / 158.4 ms | None |
| Reverse baseline, incomplete | 39.4 ms (five renders) | 154.9 ms (one save) | No samples | Editor reopen timed out after four completed clicks |
| Additional baseline | 37.2 ms | 153.8 / 161.1 ms | 168.2 / 178.2 ms | Cold switch 203.1 ms |

All completed Save samples, including the incomplete baseline's one Save, give
**155.8 ms baseline median versus 120.8 ms candidate median** (13 versus 12
samples, approximately 22% lower). Synchronous render medians were **38.5 versus
22.25 ms** across 85 versus 80 calls. Warm-restore medians were **168.5 versus
150.4 ms**, eight per revision. These small, noisy interaction samples support
the reduction in Markdown work; they do not establish a cold-navigation fix.

The incomplete reverse baseline is retained as a failure, not removed from the
record. Its fifth click, editor reopen, failed the existing readiness check.
The trace shows a background `openWorkspaceDoc(...preserveScroll:true)` and
sidebar refresh during that reopen; the exact cause still needs investigation.
It occurred with the previous renderer. Its diagnostics completed and its
owned server stopped. The four complete comparison runs had no request/Git/
browser errors, invalid clocks or request-ID/route mismatches; all measured API
requests stayed below 200 ms. No trace reached its 10,000-event bound.

### Longer verification

A final candidate run disabled call tracing and completed 20 repetitions:
**139 of 140 native clicks passed**. All 20 Save clicks passed, with **113.1 ms
median and 125.1 ms maximum**. All 18 warm document restores passed, with
**146.9 ms median and 196.5 ms maximum**. Other maxima were 90.9 ms for document
open, 68.6 ms for editor open, 181.6 ms for editor reopen, 56.9 ms for Cancel,
and 43.4 ms for close.

The overall run still **failed**: the second cold workspace switch took
**251.1 ms**, including 7.2 ms browser input queueing. One of 40 native text
setups took **202.3 ms** for a 28-character append. The earlier full multiline
`Input.insertText` failure is unchanged; these acknowledgement timings are not
physical typing/display or clipboard-paste measurements.

All **799 browser API requests** stayed below 200 ms (maximum **100.6 ms**),
as did all **828 server requests** (maximum **96.58 ms**). Every recorded
request ID/route and all 140 native input clocks passed. Sixty persistence
checkpoints checked 240 files byte-for-byte; the final four documents totaled
404,853 bytes. No browser/network/Git errors occurred. The owned server stopped.

### Verification and diagnostics

**97 focused checks passed.** JavaScript/Python syntax checks and
`git diff --check` passed. The suite covers the parser, real Chrome Markdown/copy behavior,
document saving, editor workload, sidebar navigation/ownership, dashboard
scheduling, Markdown routes, Assistant rendering/note editing and notebook
paths. The new parser test compares actual vendored Marked output on 22 source
cases, per-call renderer changes, preprocessing hooks, invalid inputs and a
1,500-section document. The latter executes zero disclosure searches on the
fast path versus 1,500 with the previous extension.

The old browser copy test referenced removed Assistant inline buttons and
failed before launching Chrome. It now exercises the current heading context
menu, retaining its section-boundary, generated-content and clipboard checks.
Additional browser assertions cover sanitization, syntax colors, exact code
text, image options and code-copy controls on the plain parser path.

The fixture accepts `--markdown-revision` for source-only comparisons. Optional
`LAB_PERF_REFRESH_TRACE=/tmp/calls.json` records bounded refresh/open/render call
metadata and durations, including on failed runs. It preserves original return
values, promise identity and exceptions and is restricted to the disposable
fixture. It does not record document source or response bodies. Its regression
checks successful, asynchronous-failing and synchronous-failing calls, scope
rejection and the event bound.

Artifacts:

- `/tmp/lab-navigation-refresh-before-{browser,server,calls}.json` and
  `/tmp/lab-navigation-refresh-docs-before-{browser,server,calls}.json` contain
  the initial attribution runs.
- `/tmp/lab-markdown-1500-{before,after,after-2,before-2,before-3}-{browser,server,calls}.json`
  and matching `.log` files retain all comparison runs, including the failure.
- `/tmp/lab-markdown-1500-final-{browser,server}.json` and `.log` contain the
  longer, untraced verification.
- `/tmp/lab-markdown-1500-comparison.json` summarizes all runs; its generator is
  `/tmp/lab-markdown-summary.py`.
- `/tmp/lab-markdown-regressions-final.log` contains the focused checks.

The goal remains active: cold workspace latency, editor input, the baseline
reopen failure, earlier misses and iTerm parity remain unresolved. No main
merge, push or live-server restart occurred. Local merge still awaits the
earlier approval after automatic review rejected it.

## Keep pending file refreshes from invalidating Edit (2026-09-23)

**Checkpoint:** fix the editor-reopen timeout discovered in the reverse
Markdown baseline. The trace at
`/tmp/lab-markdown-1500-before-2-calls.json` identifies the first interfering
`openWorkspaceDoc(...preserveScroll:true)` as the mtime interval callback. Its
filesystem request started before Edit, but returned after the editor rendered.
The callback had checked editing only before the request. `openWorkspaceDoc`
then reset `_workspaceDocEditing` to false, and a later WebSocket index update
was consequently also allowed to refresh the document. The readiness check
never passed even though the modal had rendered a textarea.

The mtime poll now checks editing again after the response and workspace/root
validation. It leaves the previous mtime baseline in place, so the same change
is still detected by the next poll after editing ends. `openWorkspaceDoc` also
rejects a preserve-scroll refresh before it changes editor/navigation state
when editing is active, covering callers such as Assistant's index handler.
If a text refresh started before editing, its delayed success or error cannot
replace the current source/view while the editor is active. Its fresh cache
entry remains available for subsequent navigation. Explicit user navigation
retains its existing behavior.

### Verification

The new deferred-response regression initially produced **five failures and
one passing read-only control** against `baec61a`: refresh entering an active
editor, editing beginning during a content read, a read error arriving during
editing, and pending mtime responses for the workspace and selected worktree.
The fix makes all these cases pass. An additional explicit-navigation control
confirms that ordinary file opening still resets editing and renders normally.
The mtime cases also verify no extra requests while editing, a retained mtime
baseline, released single-flight state, and one document/sidebar refresh after
editing ends.

**119 focused checks passed** across document refresh/save, the native editor
workload, sidebar file configuration/navigation, dashboard scheduling, notebook
paths, workspace navigation, quick files, document terminals and Markdown
routes. The initial restricted invocation passed 117 checks; two real Chrome
tests aborted before browser startup. They were rerun with the required Chrome
launch permission. JavaScript/Python syntax and `git diff --check` passed.

The isolated large-document run used 20 edit repetitions, 1,500 sections per
document, 5,000 mixed flat files and 2,500 Git changes per workspace. Normal
polling and optional refresh/file timing diagnostics stayed enabled. **All 140
clicks passed**, maximum **174.0 ms**. All 20 editor reopens completed, with
median **66.2 ms**, p95 **70.5 ms** and maximum **71.4 ms**. Both cold workspace
switches passed (152.6 and 171.8 ms), as did all 18 warm restores (maximum
172.2 ms). The observed editor timeout did not recur; the deterministic tests
provide the direct evidence for the specific race fix. This is not proof that
all possible editor races or previously slow cold switches are resolved.

The run still **failed the overall target** because two of 40 text-insertion
acknowledgements took **215.6 and 211.6 ms** for 58/59-character appends. These
remain separate from click timing and physical typing/display latency. The
previous full multiline insertion failure also remains open.

All **786 browser API requests** were under 200 ms (maximum **84.1 ms**), as
were all **815 server requests** (maximum **77.88 ms**). Request IDs/routes and
all native clocks matched. Sixty persistence checkpoints checked 240 files
byte-for-byte, ending with 404,853 bytes across the four documents. There were
no network/browser/Git errors, the trace did not reach its event bound, and the
owned server stopped. No terminal transport or typing behavior changed.

Artifacts:

- `/tmp/lab-editor-refresh-baseline-tests.log` retains the five reproduced
  failures before the production edit.
- `/tmp/lab-editor-refresh-tests.log`,
  `/tmp/lab-editor-refresh-regressions.log`, and
  `/tmp/lab-editor-refresh-browser-regressions.log` retain the focused checks
  and the initial Chrome launch failures.
- `/tmp/lab-editor-refresh-after-{browser,server,calls}.json` and `.log` retain
  the full isolated workload; `/tmp/lab-editor-refresh-summary.json` summarizes
  clicks, requests, input setup, clocks, persistence and cleanup.

The goal remains active. Cold navigation variability, editor text input,
other historical misses and iTerm parity still need work. No main merge, push
or live-server restart occurred. Main merge remains pending after the earlier
automatic approval rejection.

## Finish explicit navigation before overlapping background refreshes (2026-09-23)

**Checkpoint:** keep an index/mtime event from discarding the dashboard load
started by a workspace click. Earlier 251 ms workspace traces contained a second
background dashboard/file request batch before the first navigation finished.
A fresh, unmodified normal-navigation control passed all 40 clicks (first cold
switches 153.5 and 150.5 ms); this confirmed the overrun is intermittent, not an
invariable cost of switching these workspaces.

`showWorkspaceInfo` now tracks one explicit navigation by workspace, selected
file root and dashboard generation. Background refreshes arriving for that
same current owner share one queued completion and retain a copy of the latest
options. The original click finishes normally; the queued refresh then makes
fresh requests. A new user navigation remains immediate. Scope changes,
revisits and a newer dashboard generation invalidate the queued work, and an
older completion cannot clear a newer owner. The generation is checked both
when accepting the event and when starting its follow-up, including switching
to another worktree and back while an obsolete same-path load is pending.

The existing load body and its sidebar/dashboard guards are retained in
`_loadWorkspaceInfo`. No cache limit, filesystem behavior, polling interval,
terminal transport or readiness condition changed. Ordinary background calls
outside explicit navigation keep their prior behavior. Background sidebar
reconciliation still has its existing detached-completion semantics; the new
promise does not claim to await every subsequent sidebar paint.

### Controlled overlap measurement

The fixture's new optional `--navigation-refresh-delay 20` calls the normal
background-refresh entry point during each native workspace click. Polling
remains enabled. This deliberately controls request overlap; it is **not a
measurement of watcher or WebSocket event delivery**. Injection requires the
owned fixture and same workspace/root/generation. The report records all
requested/delivered/skipped events and checks that each workspace click received
an event before its measured completion. Missing or late delivery fails the
controlled run instead of being counted as exercised overlap. Invalid delays
or mixed workflows fail before fixture creation.

Four baseline/candidate/candidate/baseline runs each used ten workspace clicks
and ten document clicks, 5,000 mixed flat files per workspace and 2,500 actual
Git changes. Baseline source was `91c5c33`. Call/file timings were enabled equally
on both revisions, without CPU profiling. All 80 clicks and all measured APIs
passed. Every controlled event arrived within its intended measured click.

| Run order | Workspace-click median | First cold Alpha / Beta | Browser / server API maximum |
| --- | ---: | ---: | ---: |
| Baseline | 113.0 ms | 169.7 / 184.5 ms | 74.2 / 53.95 ms |
| Candidate | 100.0 ms | 137.2 / 122.6 ms | 74.8 / 62.18 ms |
| Candidate repeat | 98.7 ms | 152.8 / 114.4 ms | 96.3 / 84.54 ms |
| Reverse baseline | 102.6 ms | 187.5 / 150.1 ms | 68.5 / 51.30 ms |

Combined workspace-click medians were **111.05 → 99.0 ms** (20 samples per
revision, about 11% lower). Cold-switch medians were **177.1 → 129.9 ms** (only
four samples per revision, about 27% lower). These small controlled samples
support avoiding the interrupted first load; they do not prove every cold
switch is now below 200 ms.

With a single overlapping event, finishing the original dashboard and then
reading fresh data can perform more total requests than abandoning the first
load. These candidate runs recorded 249/252 browser requests versus 235/234 for
the baseline. The new coalescing reduces multiple events during the same
navigation to one follow-up, while preserving that follow-up's fresh reads.
Every request/route correlation and native clock passed; all owned servers
stopped, all Git/browser/network checks passed, and no call trace reached its
bound.

### Ordinary navigation and large-document editing

Without injected refreshes or call tracing, 40 workspace and 40 document clicks
all passed: **135.5 ms maximum workspace switch**, **69.4 ms maximum document
open**. All 658 browser API requests passed (maximum **84.5 ms**), as did all
687 server requests (maximum **83.45 ms**). This run preceded the final additional
generation check at queue entry; the guard was then covered by the scope-race
test and the larger editing/typing verification below.

The final guarded version completed the 20-repetition, 1,500-section editor
workflow: **139 of 140 clicks passed**. Its first cold workspace switch still
took **205.4 ms**, including 2.1 ms input queueing. All 20 saves (maximum
116.9 ms), all 20 editor reopens (72.0 ms) and all 18 warm restores (164.9 ms)
passed. All 40 native append setups passed, maximum **172.7 ms**. This remains
an overall failing click run; the first cold sample is retained.

All **792 browser API requests** passed (maximum **107.4 ms**), as did all
**821 server requests** (maximum **106.22 ms**). All clock/request correlations
passed. Sixty persistence checkpoints checked 240 files byte-for-byte, ending
at 404,853 bytes across the four documents. There were no Git/browser/network
errors and the owned server stopped. The earlier full multiline text-insertion
failure remains unresolved; a passing small-append setup does not establish
physical typing or clipboard-paste latency.

### Regression coverage and artifacts

The seven new full-load overlap scenarios all fail against `91c5c33` because
background calls immediately restart pending navigation. They now verify one
fresh follow-up after initial success/error, unchanged document ownership,
workspace/worktree changes, newer explicit navigation and A → B → A revisits.
Additional tests cover an older completion during a newer pending navigation,
and rejection of an already-obsolete same-path owner. The diagnostic checks
cover fixture scope, preserved results, delivery ownership, late/skipped events,
and CLI validation. The focused bundle also exercises sidebar rendering
ownership/configuration, editor refresh/save, notebooks, workspace navigation,
quick files and real Chrome document-terminal behavior.

Artifacts:

- `/tmp/lab-cold-refresh-before-{browser,server,calls}.json` is the fresh normal
  navigation control on `91c5c33`.
- `/tmp/lab-dashboard-overlap-{before,after,after-2,before-2}-{browser,server,calls}.json`
  and matching `.log` files retain the controlled comparisons.
- `/tmp/lab-dashboard-overlap-summary.json` and its generator
  `/tmp/lab-dashboard-overlap-summary.py` summarize all four comparisons,
  including recomputed delivery coverage for the first three runs.
- `/tmp/lab-dashboard-queue-final-{browser,server,summary}.json` and `.log`
  contain the ordinary navigation run before the final entry guard.
- `/tmp/lab-dashboard-queue-docs-{browser,server,summary}.json` and `.log`
  contain the final guarded editor workflow, including the 205.4 ms miss.
- `/tmp/lab-dashboard-queue-baseline-tests.log` retains the seven baseline
  failures; `/tmp/lab-dashboard-queue-regressions-final.log` contains the final
  focused bundle.

### Final typing check and remaining failures

Before the additional entry-generation guard, a 2,400-key native-input run at
25 ms cadence passed every 50 ms check: maximum **42.3 ms** normally and
**44.6 ms** during sidebar refreshes, with 60 file updates and 61 loaded
refreshes. Its 840 browser API requests topped out at 143.1 ms and 871 server
requests at 134.19 ms. The owned terminal and server were cleaned up.

The final guarded version was checked again with the same cadence and workload.
**2,399 of 2,400 keys passed**; one loaded-phase key (index 1422) took **50.7 ms**,
including **18.2 ms browser queueing** and **32.5 ms handler-to-render**. The
normal-phase maximum was **44.6 ms**. This remains a failing typing run, not a
rounded-down pass, and its cause has not been established. All 2,400 characters
were independently verified at parse and render, including after the ready
marker scrolled out of view. There were 60 file updates and 61 loaded refreshes.
All timestamp/transport checks passed; no browser/network/Git errors occurred.

All **789 browser API requests** remained below 200 ms (maximum **134.8 ms**),
as did all **820 server requests** (maximum **83.45 ms**). Every request ID/route
matched. The owned terminal was removed and server stopped. These are
browser-input-to-render measurements, not physical keyboard/display latency or
proof of iTerm parity.

**134 focused regression checks passed** on the final guarded version, along
with JavaScript/Python syntax and `git diff --check`. Typing artifacts are
`/tmp/lab-dashboard-queue-typing-{browser,server}.json` for the earlier passing
candidate, and `/tmp/lab-dashboard-queue-typing-final-{browser,server,summary}.json`
plus matching `.log` files for the final failing run. The 205.4 ms cold switch,
50.7 ms typing sample, prior text-insertion failures and earlier historical
misses remain in the record.

The goal remains active. No main merge, push or live-server restart occurred;
the earlier automatic approval rejection still leaves main merge pending.

## 2026-09-23 — Reuse parent-folder lookups within each sidebar tree build

The previous 50.7 ms typing miss had 18.2 ms of input-handler queueing just
as sidebar data finished arriving. A fresh profile of `eb26bb9` found
`buildSidebarTree` using 277.17 ms of sampled CPU across the run, about 17%
of the 1,635.12 ms attributed to sidebar refreshes. Both Files and Recent
construct trees, repeatedly splitting and walking shared parent paths.
This identifies avoidable work; it does not prove the cause of that earlier miss.

`buildSidebarTree` now reuses parent nodes in a Map local to one call and
finds each file's parent without allocating split/filter/slice/join arrays.
Directory metadata is applied before populating file-parent lookups. The Map
is discarded when the build returns. Original file objects/order, empty
folders, name fallbacks, symlink metadata and path normalization are preserved.
The change affects the shared workspace/Recent/vault/framework builder. No
DOM, rendering readiness condition, polling interval, network freshness rule
or retained-cache limit changed.

The final component comparison alternated baseline `eb26bb9` and candidate
200 times per layout after 25 warm-up pairs. Each fixture has 5,000 files
plus directory metadata; complete returned trees matched before timing.
These are warm Node component timings, not UI latency or cold-start results:

| Layout | Baseline median | Candidate median |
| --- | ---: | ---: |
| Flat folder | 1.030 ms | 0.448 ms |
| 50 folders | 1.553 ms | 0.599 ms |
| Deeper folders | 2.147 ms | 0.639 ms |

The comparator is `/tmp/lab-sidebar-tree-bench.mjs`; final output is
`/tmp/lab-sidebar-tree-bench-final.json`. Initial output before the final
metadata-pass guard is `/tmp/lab-sidebar-tree-bench.json`.

A single before/after browser profile used 5,000 mixed files, 2,500 real Git
changes, 2,400 keys at 25 ms cadence, 60 file updates and 61 loaded refreshes.
Sampled tree-building CPU fell from 277.17 to 108.69 ms; total sampled sidebar
refresh CPU fell from 1,635.12 to 1,298.41 ms. Both runs passed all 50 ms key
checks, but loaded-phase p95 rose from 23.7 to 27.1 ms and maximum rose from
38.6 to 47.4 ms. Thus the profile demonstrates a component improvement, not
an established end-to-end typing improvement. The profiled candidate preceded
the final guard that only populates parent lookups during the file pass.

Profile artifacts are `/tmp/lab-sidebar-profile-{before,after}-{browser,server}.json`,
matching logs, `/tmp/lab-sidebar-{cpu,trace}-{before,after}.json`, and
`/tmp/lab-sidebar-profile-comparison.json`. Both profiles validated clocks,
Git state, echoed text and transport, and stopped their owned servers.
All API requests passed: browser/server maxima were 89.5/88.64 ms before
and 90.7/88.08 ms after. Profiling overhead is included in those runs.

### Final verification without browser profiling

**117 focused regression checks passed**, including real-Chrome geometry,
fragment reuse, native drag/context actions, Pin controls, Git decorations,
cache bounds, navigation ownership and notebook paths. The new tree checks
cover normalized paths, metadata replacement, original file identity, empty
folders, removed entries and independent fresh builds. JavaScript syntax and
`git diff --check` passed. Test log: `/tmp/lab-sidebar-tree-regressions.log`.

Normal navigation passed **80/80 clicks**. Forty workspace switches had a
98.9 ms median and **154.6 ms maximum**; the two cold switches took 154.6 and
144.3 ms. Forty document opens had a 32.8 ms median and **50.5 ms maximum**.
All 654 browser API requests passed (maximum **66.3 ms**) and all 683 server
requests passed (maximum **64.94 ms**). Clock, route/request-ID, Git and browser
checks passed; the server stopped. Artifacts:
`/tmp/lab-sidebar-tree-nav-{browser,server,summary}.json` and matching log.

The final typing run **failed one of 2,400 keys**: index 2242 took
**52.9 ms**, with **1.1 ms input-handler queueing**, **31.6 ms between its
sent WebSocket frame and the next received echo frame**, and **20.2 ms from
parse to render**. The received frame contained two bytes; exact input/echo
validation independently verified both keys. A workspace-files request was
in progress, but these observations do not locate the delay within the
server, PTY or browser pipeline. Further terminal tracing is needed.
Normal-phase maximum was 37.5 ms; loaded-phase maximum was 52.9 ms. Keep this
failure: no rerun was used to replace it with a passing result.

All 2,400 characters were independently verified at parse and render,
including after scrolling. There were 60 file updates and 61 loaded refreshes.
All 826 browser API requests passed (maximum **143.7 ms**) and all 857 server
requests passed (maximum **132.77 ms**). Clock, transport, route/request-ID,
Git and browser checks passed; no long task was recorded. The owned terminal
was removed and the server stopped. Artifacts:
`/tmp/lab-sidebar-tree-typing-{browser,server,summary}.json` and matching log.

The goal remains active. This checkpoint reduces tree-building work but does
not establish a universal 200 ms UI / 50 ms terminal bound or iTerm parity.
The previous 205.4 ms cold switch, 50.7 ms typing miss, editor-input failures
and earlier historical misses remain unresolved. Main merge remains pending
after the earlier automatic approval rejection; no merge, push or live-server
restart occurred.

## 2026-09-23 — Release completed file scans without cyclic GC

The previous checkpoint's 52.9 ms typing miss included 31.6 ms between a
browser input frame and the next received echo. A new terminal trace on
`f339a8f` showed several distinct delay locations: one **51.8 ms** failure
had 28.5 ms of browser input-handler queueing; another key's PTY output waited
about 20 ms before WebSocket sending; a file-response serialization overlapped
a 32 ms server gap. That trace does not establish a single cause for every
historical miss. Artifacts: `/tmp/lab-echo-path-before-{browser,server}.json`
and log. Its owned terminal was removed and server stopped.

Added optional `--trace-gc`, requiring `--server-timings`, to the isolated
fixture. A passive callback records collection wall time, generation,
thread/request identity and object counts. It keeps at most 10,000 cycles,
reports dropped records, and removes only its own callback during cleanup.
It never changes GC thresholds, disables GC, or forces a collection. Tests
cover actual cycles, unchanged policy, exceptional cleanup, bounded records,
other callbacks and CLI rejection before fixture startup.

With detailed file tracing enabled, the observer found a **46.71 ms** GC
cycle; terminal messages were handled after that cycle ended. That run passed
all 2,400 key checks despite the pause, so this is evidence of a server delay,
not a fabricated failing key. Artifacts:
`/tmp/lab-echo-gc-before-{browser,server}.json` and log.

The file-list scanner's inner `scan` function captured its own name for
recursion. Its closure therefore retained the request's full file list,
workspace path and other captured state until cyclic GC reclaimed the group.
A new regression uses weak references to request paths and disables automatic
GC only inside that test: the baseline keeps completed request objects alive,
while the candidate releases them by ordinary reference counting. Both forms
of the final test fail against the old implementation for the intended
retention assertion. Baseline evidence:
`/tmp/lab-scan-cycle-baseline-{test,final-test}.log`.

Production now passes the recursive callable explicitly. The scanner no
longer captures itself. Traversal order, depth/skip rules, symlinks, pending
notebook state, checkout annotations, response serialization and guarded-worker
behavior are unchanged. There is no callback clearing when a request times
out; a worker still traversing a slow volume keeps the callable it needs.
GC policy and polling remain unchanged.

### Comparison with detailed file tracing disabled

Both runs used 5,000 mixed files, 2,500 real Git changes, 2,400 keys at 25 ms
cadence and background file updates. Only terminal/echo timing, the passive
GC observer and ordinary request timing remained enabled. Statistics below
cover GC cycles starting between the first input and final key render:

| Measure | Baseline | Candidate |
| --- | ---: | ---: |
| Cycles observed | 673 | 652 |
| Objects reclaimed by cyclic GC | 529,843 | 13,755 |
| Total collection wall time | 244.43 ms | 127.25 ms |
| Longest collection | 21.86 ms | 12.33 ms |
| Collections over 10 ms | 6 | 1 |
| Normal typing maximum | 45.4 ms | 42.7 ms |
| Loaded typing maximum | 48.9 ms | 41.8 ms |

This is one before/after diagnostic pair; total request counts differ slightly
with asynchronous polling. Both passed all key/API limits and verified exact
echoes including scrolling. The lifetime regression independently demonstrates
the removed retention cycle. The comparison is saved in
`/tmp/lab-scan-cycle-gc-comparison.json`; source artifacts are
`/tmp/lab-echo-gc-light-{before,after}-{browser,server}.json` and matching logs.
All observers remained within their bounds, and both owned terminals/servers
were cleaned up.

Forty alternating full-ASGI comparisons against `f339a8f`, with 5,000 mixed
files and symlink fixtures, produced **identical complete JSON responses**.
Median scan/serialization time was essentially unchanged: 18.42 vs 18.35 ms;
maxima were 24.88 vs 21.86 ms. The benefit is prompt release and reduced later
collection work. Alternating variants share one runtime, so these scan timings
are not an independent GC comparison. Artifact: `/tmp/lab-scan-cycle-asgi.json`.

**89 focused checks passed**, covering workspace routes, filesystem guards,
worktree annotations and diagnostics. After making the lifetime-test tracking
stub independent of pathlib constructor versions, its final check plus the
20 diagnostics tests passed again (**21 checks**). Logs:
`/tmp/lab-scan-cycle-{regressions,final-tests}.log`. `git diff --check` passed.

### Final UI verification without detailed tracing

The final typing run enabled ordinary request timing only: no file-function,
PTY, echo-process or GC tracing. **All 2,400 keys passed 50 ms**. Maxima were
**44.9 ms** normally and **40.1 ms** during file updates. Every character was
independently verified at parse and cursor-row render, with 88 scrolled reads
in each verifier. There were 60 file updates and 60 loaded refreshes. All
**802 browser API requests** passed (maximum **133.0 ms**), as did all
**833 server requests** (maximum **117.14 ms**). Clock, transport, Git,
route/request-ID and browser checks passed. No long task was recorded; owned
terminal removal and server shutdown were confirmed. Artifacts:
`/tmp/lab-scan-cycle-typing-final-{browser,server,summary}.json` and log.

The 1,500-section document workflow passed **140/140 clicks**. Its two cold
workspace switches took **167.2 / 191.1 ms**. Twenty Saves topped out at
**118.4 ms**, twenty editor reopens at **167.4 ms**, and eighteen remembered
workspace restores at **169.3 ms**. All 60 persistence checks passed, reading
240 files; final verified content totalled 404,853 bytes across four documents.

The document run still **failed overall**: one of its 40 short append-mode
editor input setups took **203.85 ms** for 59 characters. That is CDP
`Input.insertText` setup latency, distinct from the measured clicks and from
clipboard paste. Its exact-content verification passed. Keep this failure;
there was no replacement rerun. All **793 browser API requests** passed
(maximum **70.2 ms**) and all **822 server requests** passed (maximum
**66.01 ms**). Clocks, request correlation, Git and browser checks passed;
the server stopped. Artifacts:
`/tmp/lab-scan-cycle-docs-final-{browser,server,summary}.json` and log.

The goal remains active: this fixes one confirmed server-pause mechanism,
while the editor setup failure, earlier historical misses, broader UI/API
coverage and physical/iTerm parity remain unresolved. No main merge, push or
live-server restart occurred. Main merge remains pending after the earlier
automatic approval rejection.

## Native editor keys and IME setup remain separate (2026-09-23)

This checkpoint adds diagnostic coverage; it makes **no production editor
change**. The previous 203.85 ms editor setup failure remains recorded above.

### Control experiment and trace limits

A verbose trace of the existing 1,500-section append workflow saved 323 MB
and about 813,000 events. Its event range covers only the first ~5.9 seconds,
while the CPU profile spans ~66 seconds. It cannot explain the later 221.68 ms
IME setup failure at sample 67. The traced run also missed 97/140 click
budgets; these heavily instrumented timings are not production latency claims.
Artifacts: `/tmp/lab-editor-append-before-{browser,server,trace,cpu}.json`,
`/tmp/lab-editor-append-before.log`, and
`/tmp/lab-editor-append-trace-summary.{py,txt}`. Input setup records now include
sample numbers and start/end epochs so coverage can be checked directly.

The first three IME setups are covered by the trace. They took approximately
158–165 ms to acknowledge, while their visible `TypingCommand::InsertText`
events lasted about 9–14 ms. Most CPU samples are native `(program)` time;
that alone does not identify a Chrome subsystem or a Lab handler.

A separate plain-textarea control used Chrome 153.0.8010.53, the same
1,500-section source and textarea font/spacing, a 900 px textarea, and a
1440×1000 viewport. Twenty short multiline appends were alternated with an
experimental `contain:content` variant. Twenty single native keys per variant
were then measured in the same control. These are different input workloads,
not a claim that identical text takes the same two paths:

| Input/control | Acknowledgment median / max | Paint-opportunity median / max |
| --- | ---: | ---: |
| Multiline IME append, ordinary textarea | 159.06 / 187.13 ms | 161.4 / 189.8 ms |
| Multiline IME append, CSS containment | 159.09 / 183.68 ms | 161.1 / 186.3 ms |
| Single native key, ordinary textarea | 3.17 / 5.91 ms | 16.8 / 21.9 ms |
| Single native key, CSS containment | 3.13 / 4.13 ms | 16.2 / 22.5 ms |

Every control verified exact source plus inserted text and trusted input.
Containment provided no meaningful improvement, so no CSS change was made.
Artifacts and executable controls: `/tmp/lab-editor-append-control.{mjs,json}`
and `/tmp/lab-editor-key-control.{mjs,json}`. Both owned browsers completed and
were removed. These are neither clipboard-paste nor physical-display results.

### Added native-key workload

`--document-edit --document-typing` adds fixed-cadence native input before
Save and Cancel. It sends timestamped letters, digits, spaces, Enter and Tab
at 25 ms intervals without waiting for preceding CDP acknowledgments. The
ordinary production Tab handler still inserts four spaces. Trusted key events,
current clock mapping, exact textarea value, selection, focus and connected
identity are checked after every edit and at a subsequent animation-frame
task. Coalesced paints retain the latest input index; they are not discarded.
All four fixture files remain independently verified after Save/Cancel/Close,
and modal plus inline content must include the saved native text.

The native-key results are separate from `inputSetups` and from click results.
The existing 200 ms click, API and IME-setup failure gates are unchanged; native
editor keys also have a 200 ms gate. A native-key pass cannot hide a failed
setup. The probe is limited to the disposable Alpha/Beta documents, cleans up
its listeners, and retains records when clock validation fails.

**17 focused checks passed** for document scope/content, native event/value/
cursor/paint checks, missing or corrupted input, listener cleanup, independent
input dispatch, failure retention and clock mapping. The first sandboxed test
run could not start Chrome for an existing native-clock test; the approved
isolated-browser run passed. Final log:
`/tmp/lab-editor-native-tests-final.log`. The small native smoke run passed
110 keys (maximum 23.5 ms) and all 14 clicks; artifacts:
`/tmp/lab-editor-native-smoke-{browser,server}.json` and log.

### Full fixture result, including failures

The extended workflow used 1,500 sections per document, 5,000 mixed files per
workspace, 2,500 real Git changes, 20 alternating workspace visits and normal
polling. Ordinary request timing was enabled; no CPU, Blink, file-function,
terminal or GC tracing was enabled.

| Native input | Count | Median | Maximum |
| --- | ---: | ---: | ---: |
| Letters, digits and spaces | 1,002 | 11.9 ms | 26.8 ms |
| Enter | 80 | 14.75 ms | 25.6 ms |
| Tab | 40 | 24.6 ms | 47.0 ms |

**All 1,122 native keys passed**. All exact-value, cursor, focus and clock
checks passed; 13 samples shared a paint opportunity with a later key. This
is browser input-to-paint-opportunity evidence, not observed physical pixels.

The run **failed overall**. It passed **139/140 clicks**, with one Alpha
workspace restore at **200.8 ms** (sample 127, including 7.2 ms input queueing).
The two cold workspace clicks were under budget, with a maximum of 186.5 ms.
The failing restore started its first API request about 67.2 ms after input;
its file list took 35 ms and Git status 50.1 ms. These correlated timings
narrow the investigation but do not identify the remaining frontend cost.

One of 40 IME setups also missed: sample 32, Save Alpha, **236.39 ms**. Median
setup time was 169.97 ms. This failure is retained alongside the earlier
203.85 ms failure; native-key coverage does not replace the IME measurement.
There was no replacement rerun to obtain a pass.

All **815 browser API requests** passed (maximum **109.8 ms**), as did all
**844 server requests** (maximum **107.45 ms**). Request IDs/routes, clocks,
real Git state and browser/transport errors checked cleanly. All 60 file
verification steps passed, reading 240 files; final content was 405,464 bytes
across four files. The owned server stopped and browser cleanup completed.
Artifacts: `/tmp/lab-editor-native-large-{browser,server,summary}.json` and log.

The remaining work includes the 200.8 ms workspace restore, occasional IME
setup misses, broader UI/API coverage and unmeasured physical/iTerm parity.
No main merge, push or live-server restart occurred. Main merge remains
pending after the earlier automatic approval rejection.

## Update workspace history before clearing the outgoing view (2026-09-23)

The native-editor checkpoint exposed a 200.8 ms remembered-workspace restore.
A CPU/call-timing diagnostic retained four restore misses (maximum 225.2 ms),
and V8 position ticks placed 361 ms of aggregate self time at the
`history.pushState` statement in `goToWorkspace`. The first workspace request
in its slow restores began about 60–67 ms after input. Artifacts:
`/tmp/lab-restore-before-{browser,server,cpu,calls}.json` and log. These sampled
CPU/call timings are diagnostic, not the final performance result.

### Confirmed synchronous style/layout work

The old order called `_swapViewState` before `history.pushState`. Teardown
removed the previous view's body classes, then the history update could force
Chrome to process that temporary style state before destination selection
added its classes again.

A six-visit control without native editor keys had history calls around
0.2–1.1 ms. Adding the existing native-key workload reproduced two calls at
**54.3 and 47.0 ms**. The trace places **49.19 and 42.47 ms** of style updating
inside those calls, covering **36,575 and 36,581 elements**, followed by small
layout events. This identifies actual work within the history call; it does
not infer a browser subsystem from anonymous native CPU time.

Production now updates history **before** tearing down the outgoing view.
The URL parameters, hash, state object, entry count, replacement-navigation
behavior and synchronous destination dispatch stay the same. Teardown still
closes menus/Assistant documents and parks the previous terminal before clearing
its workspace identity. An explicitly requested delete target is restored only
after teardown. Sidebar/document caches, rendering, polling and bounds did not
change.

The same six-visit diagnostic after the change produced:

| Measure | Before | After |
| --- | ---: | ---: |
| Longest history push | 54.3 ms | 3.1 ms |
| Style/layout time inside the two slow baseline pushes | 49.96 / 42.89 ms | No such events in any push |
| Longest remembered-workspace restore | 210.4 ms | 172.3 ms |
| Remembered restore median (four samples) | 168.05 ms | 164.85 ms |
| Click budget misses | 1/42 | 0/42 |

This is one short before/after diagnostic pair, not a universal latency claim.
Both runs verified 330 native editor keys, all saved/cancelled files, and both
document views. Artifacts:
`/tmp/lab-history-keys-{before,after}-{browser,server,cpu,calls,trace}.json`,
matching logs, and `/tmp/lab-history-layout-comparison.json`.
The no-native-key control is `/tmp/lab-history-before-*`.

The optional call observer now times history methods while preserving their
receiver, arguments, return value and exceptions; it never reads or records
history state payloads. `LAB_PERF_TRACE_CATEGORIES` permits a focused trace,
retaining the original verbose default. This comparison used
`devtools.timeline,blink.user_timing`, yielding complete ~13–22-second traces
instead of the previous ~6-second verbose capture. A `.metadata.json` sidecar
records categories, start/end epochs and the native completion result. Both
native-key traces reported `dataLossOccurred: false`, and event ranges cover
the final measured clicks.

### Navigation and history validation

**155 focused checks passed**, covering navigation/races, deletion guards,
workspace tab order, server views, Home/terminal ownership and UI behavior,
document source/persistence, diagnostic ownership and native input clocks.
Log: `/tmp/lab-history-regressions-final.log`. Syntax and whitespace checks
passed. The new outgoing-view regression fails against `3ff7993` for the
intended reason: history observes cleared classes and no workspace. This
baseline ran from an in-memory copy of the old source; production files were
not replaced. Log: `/tmp/lab-history-baseline-regression.log`.

`--document-edit --document-history` additionally traverses the real Chrome
history stack Back and Forward. It checks exact complete headings/paragraphs,
saved source, modal/edit state, every fixture sidebar file's root, and all four
persisted files. History entry IDs and URLs must remain identical, with only
the current index changing. It refuses foreign origins/roots before navigation.
Timing is reported separately as a CDP-command-to-verified-paint/controller
round trip, including CDP overhead; it is not a native key timestamp or a
physical-display measurement. Its 200 ms gate cannot hide a failed click or
IME setup. A small smoke run passed Back/Forward at 25.27/12.11 ms; artifacts:
`/tmp/lab-history-stack-smoke-{browser,server}.json` and log.

### Final large-document result, including the remaining misses

With 1,500 sections, 5,000 mixed files per workspace, 2,500 real Git changes,
20 alternating visits and ordinary request timing only:

- **All 18 remembered-workspace restores passed**, maximum **174.0 ms**.
- **139/140 clicks passed**. The first cold workspace click still missed at
  **205.7 ms**, including 1.9 ms input queueing. Its file-list request started
  4 ms after input and took **95.6 ms** in Chrome / **91.52 ms** inside ASGI;
  dashboard requests began about 104.9 ms after input. This is separate from
  the removed history stall and remains a useful next profiling target.
- **All 1,122 native editor keys passed the 200 ms UI budget**, maximum
  **58.4 ms** on Tab. Exact value/cursor/focus and clock checks passed; 17
  samples shared a paint opportunity with later input. This does not claim
  that every editor key stayed below the terminal's stricter 50 ms target.
- Real browser Back/Forward passed at **156.46 / 138.36 ms**, including exact
  final saved content and unchanged history entries.
- **One of 40 IME setups failed**, Save Alpha sample 32 at **269.79 ms**.
  This result remains alongside the earlier setup failures; no replacement
  run was used to obtain a pass.
- All **840 browser API requests** passed (maximum **95.6 ms**); all
  **869 server requests** passed (maximum **91.52 ms**). Request IDs/routes,
  clocks, Git state and browser/transport checks passed.

The document run therefore **failed overall**. All 62 persistence steps
(including history) passed, reading 248 files; final content totalled 405,464
bytes across four files. The owned server/browser stopped. Artifacts:
`/tmp/lab-history-final-docs-{browser,server,summary}.json` and log.

### Final terminal typing verification

Without CPU, layout, file-function, PTY or GC tracing, **all 2,400 terminal
keystrokes passed 50 ms**. Maxima were **37.5 ms** normally and **39.7 ms** with
60 file updates and 61 sidebar refreshes. Independent parse and cursor-row
render checks verified every character, including 87 scrolled reads per
verifier. No long task, clock, transport or browser error was recorded.

All **785 browser API requests** passed (maximum **119.1 ms**) and all
**816 server requests** passed (maximum **90.14 ms**); request IDs/routes and
real Git state matched. The owned benchmark terminal was removed and its
server stopped. Artifacts:
`/tmp/lab-history-final-typing-{browser,server,summary}.json` and log.
This is validation after the navigation change, not evidence that reordering
history itself caused the lower terminal maxima.

The goal remains active: cold navigation and IME misses, broader UI/API
coverage and physical/iTerm parity are unresolved. No main merge, push or
live-server restart occurred. Main merge remains pending after the earlier
automatic approval rejection.

## Overlap cold dashboard reads with file discovery (2026-09-23)

The previous checkpoint's cold click waited for a 95.6 ms browser file-list
request before starting five independent dashboard reads. The cold path now
dispatches the file request first, then starts the existing dashboard batch
while discovery is pending. Request order matters: starting dashboard reads
before files previously congested Chrome's connection pool. Starting them
after dispatch avoids that reversal while removing the completion dependency.

The callback runs once. The original file promise is still awaited and its
failure is observed even if the callback throws. Complete file data and the
existing workspace/root/generation checks still precede sidebar publication.
Warm, cached and background scheduling, full document/sidebar readiness,
polling, cache bounds and backend behavior are unchanged.

### Fixed A/B/B/A comparison

Four predetermined short runs compared baseline `2489ef9` with the candidate,
using 1,500-section documents, 5,000 mixed flat files per workspace and 2,500
real Git changes. Each run included two cold workspace clicks and 12 document
actions. Only ordinary server request timing was enabled.

| Run | Cold Alpha | Cold Beta | Click misses | IME misses |
| --- | ---: | ---: | ---: | ---: |
| Baseline A1 | 200.4 ms | 187.9 ms | 1 | 0 |
| Candidate B1 | 152.5 ms | 186.7 ms | 0 | 0 |
| Candidate B2 | 148.9 ms | 156.3 ms | 0 | 0 |
| Baseline A2 | 130.9 ms | 173.1 ms | 0 | 0 |

Across four cold samples per variant, the median was **180.5 → 154.4 ms**
and maximum **200.4 → 186.7 ms**. File request durations varied: 38.5–95.7 ms
for the baseline and 46.3–51.3 ms for the candidate. The entire click change
cannot be attributed to overlapping requests. Resource timing independently
confirmed the intended scheduling: candidate dashboard actions began
**0.1–0.3 ms after file dispatch**, rather than after discovery completed.
The baseline failure remains in the report; there were no replacement runs.
Artifacts: `/tmp/lab-cold-overlap-abba.json`,
`/tmp/lab-cold-overlap-{a1,b1,b2,a2}-{browser,server}.json` and matching logs.

### Scan diagnostics and regression checks

The optional synchronous handler/function observers now report thread CPU
alongside elapsed time. Async observers omit thread CPU because another task
can execute on that thread during an await. Both synchronous measurements
include nested work and must not be summed across nested observations.

The earlier 91.52 ms cold ASGI response was not reproduced in the detailed
diagnostic runs. One cold worker took 28.49 ms elapsed / 20.04 ms thread CPU;
its waiting handler used under 1 ms CPU. Later file requests reached 59.15 ms,
sometimes overlapping ~9–10 ms GC pauses, and sometimes without significant
GC. This does not identify or fix the rare cold scan delay. Per-notebook
tracing adds work, so final latency claims exclude these observers. Artifacts:
`/tmp/lab-cold-scan-{before,cpu}-{browser,server}.json` and logs. The full CPU
diagnostic retained four IME misses, maximum 280.98 ms; all 140 clicks passed.

**204 focused checks passed**, covering sidebar/dashboard races and errors,
navigation/history, deletion, workspace tabs/proxies, Home/terminal ownership,
native pins, document editing/input and timing observers. The new ten-case
cold-read regression holds file discovery pending and checks dispatch order,
one callback, deferred painting, changed scopes/generations and both failure
paths without unhandled rejections. The success case fails against the old
source for the intended reason: dashboard work has not started while files
are pending. That baseline was loaded in memory without replacing production
files. A deterministic CPU-clock test distinguishes waiting from synchronous
CPU and prevents async attribution. Syntax and whitespace checks passed.
Logs: `/tmp/lab-cold-overlap-tests.log`,
`/tmp/lab-cold-overlap-regressions-final.log`, and
`/tmp/lab-cold-overlap-baseline-regression.log`.

### Final large-document validation

The same large fixture, 20 alternating visits, native editor keys and actual
browser history ran without CPU, file-function, layout or GC tracing:

- **All 140 clicks passed 200 ms**, maximum **177.3 ms** on a remembered
  workspace restore. Cold workspace clicks were **166.4 / 154.8 ms**; all
  18 remembered restores passed. Dashboard requests overlapped discovery.
- **All 1,122 native editor keys passed 200 ms**, maximum **50.8 ms** on Tab.
  Exact value/cursor/focus and clocks passed; 13 keys shared a paint opportunity
  with later input. This does not apply the terminal's 50 ms budget to editors.
- Back/Forward passed at **140.46 / 136.67 ms**, including complete saved
  content, correct sidebar roots and unchanged history entries.
- **One of 40 IME insertions failed**, Cancel Beta sample 55 at **202.11 ms**.
  The run therefore **failed overall**; no replacement run was used to pass.
- All **833 browser API requests** passed, maximum **156.3 ms**; all
  **862 server requests** passed, maximum **154.26 ms**. Both maxima were Git
  status. A later file response reached **124.28 ms** inside ASGI, so scan
  variability remains unresolved even though cold clicks passed in this run.

Request IDs/routes, Git state and browser/transport checks were clean. All
62 persistence checks passed, reading 248 files; final content was 405,464
bytes across four files. The owned browser/server stopped. Artifacts:
`/tmp/lab-cold-overlap-final-docs-{browser,server,summary}.json` and log.

### Final terminal typing validation

With detailed diagnostics disabled, **all 2,400 terminal keystrokes passed
50 ms**. Maxima were **38.6 ms** normally and **48.8 ms** with 60 file updates
and 61 sidebar refreshes. Independent parse and cursor-row render checks
verified every character, including 87 scrolled reads per verifier. No clock,
transport, browser error or long task was recorded. Normal polling and
WebSocket compression settings were unchanged.

All **798 browser API requests** passed, maximum **119.8 ms**, and all
**835 server requests** passed, maximum **98.31 ms**. Request IDs/routes and
real Git state matched. The owned benchmark terminal was removed and its
server/browser stopped. Artifacts:
`/tmp/lab-cold-overlap-final-typing-{browser,server,summary}.json` and log.
This validates the checkpoint; it does not attribute terminal performance to
the cold dashboard scheduling change or establish physical/iTerm parity.

All eight owned servers in this checkpoint's two diagnostics, four A/B/B/A
runs and two final validations report `serverStopped: true`. The goal remains
active: occasional IME insertion misses, variable scan delays, broader UI/API
coverage and physical/iTerm parity are unresolved. No main merge, push or live
server restart occurred. Main merge remains pending after the earlier
automatic approval rejection.

## Keep notebook session metadata independent of Jupyter imports (2026-09-23)

### Remaining IME cost and expanded coverage

A four-insertion plain-textarea diagnostic again reproduced **147.8–175.4 ms**
acknowledgments without Lab. It kept the same 1,500-section source and short
multiline revisions; every resulting value matched and each insertion emitted
three or four trusted input events. The trace's `TypingCommand::InsertText`
spans were only **6.42–15.78 ms**, so they do not explain the entire delay.
The trace reported no data loss and retained all four insertions. No editor
behavior was changed on this evidence and the earlier 202.11 ms miss remains.
Artifacts: `/tmp/lab-ime-native-trace.mjs`,
`/tmp/lab-ime-native-trace.json`, and
`/tmp/lab-ime-native-trace-control.json`. Chromium's
[InputHandler source](https://chromium.googlesource.com/chromium/src/%2B/master/content/browser/devtools/protocol/input_handler.cc)
confirms the CDP operation routes through IME commit; it is not a clipboard
paste measurement.

The new `--notebook-view` workflow extends coverage to actual notebook opens,
remembered-workspace restores, code hiding/showing, and output folding/unfolding.
It uses timestamped native clicks and the unchanged 200 ms budget, full cells
and normal polling. Each workspace owns a 200-cell notebook (alternating
formatted Markdown and Python source with 20-line stream outputs). Readiness
checks every cell's ID/index/type, complete source and highlighted text,
complete output, and enabled controls. Toggle state must match the requested
action. Both notebooks must remain byte-identical after each six-action visit.

The fixture is created only under the existing CLI-created disposable vault,
refuses mixed workflows and foreign scopes, and never clicks execution or
mutation controls. The final request log separately confirms no notebook
mutation requests. This does not yet cover rich-output rendering, notebook
editor typing, execution/interrupt latency or all notebook controls.

### Identified cold dependency and production change

The first diagnostic `/api/nb/session` response took **63.21 ms**. Its handler
imported `core.notebook_kernel` solely to obtain a deterministic session name,
loading the Jupyter execution stack before returning metadata. Session metadata
now imports a lightweight shared `core.notebook_identity` module. The kernel
uses that same identity calculation, so there is no duplicated implementation.

The resolved vault path, live workspace metadata ID, legacy directory handling,
relative notebook path, hash and `local-` prefix are unchanged. The endpoint
retains path validation, provider and all capability fields. Kernel startup,
thread ownership, session reuse, execution, cancellation and shutdown code did
not change. No identity cache, extra background task or eager import was added.

A cold-process regression prevents importing either the execution module or
Jupyter while requesting metadata. It fails on the original production route
for the expected import, then passes after the change. Separate identity checks
cover renamed folders, fresh metadata IDs, separate vaults/notebooks, legacy
`projects` directories and vault symlink aliases. **107 checks passed**,
including real Jupyter execution, CLI/human shared state, streaming, restart,
interrupt, cancellation and a workspace rename that preserves kernel variables.
Logs: `/tmp/lab-notebook-identity-baseline-regression.log`,
`/tmp/lab-notebook-identity-tests.log`, and
`/tmp/lab-notebook-identity-regressions.log`. Syntax/whitespace checks passed.

### Native notebook measurements

Both ordinary runs used 20 alternating visits, 5,000 mixed flat files per
workspace and 2,500 real Git changes. CPU/layout/function/GC diagnostics were
disabled. Every one of the **120 clicks passed** in each run.

| Measurement | Before | After |
| --- | ---: | ---: |
| First session metadata response, ASGI | 62.66 ms | 8.55 ms |
| First notebook open | 156.3 ms | 148.3 ms |
| Longest notebook open | 156.3 ms | 148.3 ms |
| Longest remembered-workspace restore | 157.5 ms | 170.2 ms |
| Longest show/hide code action | 48.1 ms | 49.5 ms |
| Longest output fold/unfold action | 43.8 ms | 43.8 ms |

This is one before/after pair. The first metadata response improved markedly,
but other work and scheduling varied; it does not establish a universal UI
speedup. The final run passed **470 browser API requests** (maximum **102.6 ms**)
and **498 server requests** (maximum **100.40 ms**). All native clocks, request
IDs/routes, Git checks and browser/transport checks passed. Twenty persistence
checks read 40 files; both notebooks remained unchanged, totalling 264,642
bytes. Artifacts: `/tmp/lab-notebook-view-{baseline,final}-{browser,server,summary}.json`,
matching logs, and `/tmp/lab-notebook-view-comparison.json`.

A matching six-visit trace pair retained the cold metadata improvement
**63.21 → 18.21 ms**, with first opens **179.5 → 121.2 ms**. Notebook rendering
dependencies began 69.6 ms after the notebook request before, and 27.9 ms after
it afterward. Remaining work includes sequential dependency loading and full
cell rendering; neither was changed in this checkpoint. Both traces reported
no data loss and their event ranges cover the final clicks. The before trace
also retained a **215.4 ms cold workspace miss**, with a **104.95 ms ASGI file
response**. That separate scan variability remains unresolved. Artifacts:
`/tmp/lab-notebook-view-{before,after}-{browser,server,cpu,trace}.json`, trace
metadata sidecars, logs, and `/tmp/lab-notebook-view-trace-comparison.json`.

The initial 12-click smoke and all four subsequent notebook runs stopped their
owned browsers/servers. The goal remains active, including IME/cold-navigation
outliers, broader UI/API/typing coverage and physical/iTerm parity. No main
merge, push or live-server restart occurred; main merge remains pending after
the earlier automatic approval rejection.

## Reduce polling snapshot bookkeeping (2026-09-23)

### Evidence for concurrent watcher work

A coarse diagnostic captured an **83.43 ms** file-list response. Its filesystem
worker took **73.32 ms elapsed / 32.09 ms thread CPU**, overlapping both
5,000-entry watcher snapshots (84.81/92.74 ms elapsed, about 38.9 ms CPU each).
No GC pause over 1 ms overlapped that request. A later 79.42 ms response also
overlapped both snapshots. Other slower requests overlapped filesystem workers
without watcher snapshots, so this is not a complete explanation of all delays.

`--trace-watchers` now observes entire snapshots, diffs, watch refreshes and
index rebuilds. Records omit paths/content, are bounded under concurrent
callbacks and retain elapsed/thread CPU separately; every method is restored
on exit. `--trace-file-scans` retains the handler/worker/serialization observers
while omitting per-notebook lookup tracing. Both require a server timing
sidecar. Normal polling, event delivery, rebuilds and GC policy stay intact.
These are isolated diagnostics, not production hooks or final latency claims.

### Production change and equivalence

Lab's polling observer now uses a private snapshot subclass. Fresh native
`DirEntry` paths and stats replace repeated path joining and per-file context
manager construction. The traversal retains only directories for recursion,
while keeping the original enumeration-before-stat ordering and error handling.
Links are followed as before, and custom stat/listing adapters use the upstream
traversal. There is no cross-poll metadata cache.

The completed private snapshot supplies its dictionary key view to watchdog's
existing set comparisons, avoiding eight full path-set copies per diff. Its
path map is never changed after construction. Watchdog's event comparison,
queue, polling wait and observer lifecycle are unchanged, as are Lab's watch
scopes and debounce. Native/FSEvents/kqueue choices are unaffected. This uses
the emitter's snapshot factory; dependency upgrades must retain that seam.

**177 distinct focused checks passed**. The 176-check regression run covered
native polling-to-WebSocket propagation, index/workspace changes, rename/delete,
notebooks and benchmark guards. After synchronizing the diagnostic record bound,
all 25 observer checks passed, including one additional concurrency case.
Snapshot comparisons cover file/directory creation, removal, moves, modification,
atomic replacement, hard links, directory/file symlinks, missing targets,
recursive/non-recursive trees, Unicode/byte paths, custom adapters, permissions
and deletion between enumeration and stat. No test changes the production
polling interval to obtain a latency pass. Logs:
`/tmp/lab-watcher-snapshot-regressions.log` and
`/tmp/lab-watcher-observer-final-tests.log`.

### Component and concurrent-work measurements

`scripts/perf/lab_watcher_snapshot_latency.py --files 5000 --samples 40`
alternates the upstream and candidate snapshots on the same owned static tree.
It retains all 80 observations and checks paths, inode maps and every field
used for event detection. It is a component comparison after fixture creation
and reference validation, not a cold UI measurement.

| Component median | Upstream | Candidate |
| --- | ---: | ---: |
| Snapshot elapsed | 15.72 ms | 12.73 ms |
| Snapshot thread CPU | 15.72 ms | 12.73 ms |
| Diff elapsed | 3.51 ms | 2.98 ms |
| Diff thread CPU | 3.51 ms | 2.98 ms |

Artifact: `/tmp/lab-watcher-snapshot-component-final.json`. The preliminary
component experiment also reduced snapshot/diff medians (12.34→9.98 and
2.88→2.46 ms); absolute times varied between runs. Artifact:
`/tmp/lab-watcher-component.json`.

The matching 20-visit diagnostic pair used 200-cell notebooks, 5,000 mixed
files and 2,500 real Git changes per workspace. All 120 clicks passed in each
run. Large-snapshot medians changed **15.59→12.43 ms elapsed** and
**15.42→12.21 ms CPU**; their maxima changed 98.42→50.65 ms. File-response
maxima were **83.43→48.44 ms**, while medians were **35.13→36.16 ms**.
The candidate cold request did not overlap either snapshot, so the entire cold
click change (186.4→165.1 ms) cannot be attributed to faster snapshot work.
No diagnostic records were dropped. Both servers stopped. Artifacts:
`/tmp/lab-watcher-overlap-{before,after}-{browser,server}.json`, logs, and
`/tmp/lab-watcher-overlap-comparison.json`.

### Final validation with detailed diagnostics disabled

The fixed sequence used the same 5,000 mixed files and 2,500 Git changes per
workspace, normal lifecycle/polling and ordinary request timing only:

- **Notebook:** all **120 clicks passed**, maximum **170.0 ms**. All 200
  cells' identities/source/highlights/outputs and controls were checked. Twenty
  persistence checks read 40 files; the two notebooks remained byte-identical
  at 264,642 bytes. No notebook mutation request occurred. All **470 browser
  API requests** passed (maximum **84.3 ms**) and all **498 server requests**
  passed (maximum **82.43 ms**).
- **Documents:** all **140 clicks passed**, maximum **184.2 ms**. All **1,122
  native editor keys** passed 200 ms, maximum **58.4 ms**; 10 keys shared a
  paint opportunity with later input. Back/Forward passed at **168.21/161.21 ms**.
  All 62 persistence checks passed, reading 248 files and verifying 405,464
  final bytes across four files. All **840 browser API requests** passed
  (maximum **79.5 ms**) and all **869 server requests** passed (maximum
  **78.74 ms**). However, **two of 40 IME insertions failed**: Save Alpha
  sample 18 at **259.69 ms** and Cancel Alpha sample 132 at **249.11 ms**.
  The document run **failed overall**; these failures were retained without
  replacement runs.
- **Terminal:** all **2,400 keys passed 50 ms**, maximum **36.1 ms** normally
  and **48.7 ms** during 60 document updates and 60 sidebar refreshes. Independent
  parse and cursor-row rendering checks verified every character, including
  88 scrolled reads per verifier. No long task, clock, transport or browser
  error occurred. All **786 browser API requests** passed (maximum **100.6 ms**)
  and all **817 server requests** passed (maximum **99.54 ms**).

All runs passed request-ID/route correlation, real Git and native-clock checks.
CPU/file-function/layout/watcher/GC diagnostics were disabled, and WebSocket
compression retained its production setting. The owned terminal was removed;
all three final browsers/servers and both diagnostic servers stopped. These
checks validate the candidate; they do not attribute each end-to-end timing
change to the snapshot implementation or establish physical/iTerm parity.
Artifacts: `/tmp/lab-watcher-final-{notebooks,docs,typing}-{browser,server,summary}.json`,
matching logs, and `/tmp/lab-watcher-final-runs.json`.

The goal remains active. IME insertion misses, previously observed cold-navigation
outliers, broader UI/API/typing coverage and physical/iTerm parity are unresolved.
No main merge, push or live-server restart occurred; main merge remains pending
after the earlier automatic approval rejection.

## 2026-09-23 — Type during continuous terminal output

Added `--typing-output` to the disposable native typing fixture. It runs an
owned raw TUI that writes 40 colored scrolling log lines every 50 ms above a
six-row input footer. The footer retains the last 64 characters with a numeric
source offset. Independent parsing and rendering readers require exact input,
continuous prior verification, and no output ahead of native key events. Partial
transport frames remain pending. Output coverage comes from valid log text in
actual xterm render callback ranges, with progression required in both phases.
The phases are named `output` and `output-sidebar-refresh`; the existing quiet
workload, cadence, budget and readiness checks remain unchanged.

The required server sidecar retains source output batches, byte/line totals,
input byte count/SHA-256 and geometry. Optional `--trace-terminal` records input
receipt and footer-write times in this report, separately from the ordinary echo
protocol. Export verifies ownership of the fixture pane PID, snapshots between
producer operations, and leaves normal terminal cleanup responsible for exit.
No production code or user terminal changed in this checkpoint.

All three native runs retained their failures:

- **Smoke:** 400 keys, maximum **52.6 ms**. Every input character was parsed and
  rendered; both phases displayed thousands of scrolling lines. No validation,
  clock or transport error. Artifacts: `/tmp/lab-output-typing-smoke-{browser,server}.json`.
- **Large workload:** 5,000 mixed files and 2,500 Git changes per workspace,
  2,400 native keys, 60 real file updates and 61 refreshes. **15 keys failed
  50 ms**, maximum **58.1 ms** in output and **54.6 ms** in output plus sidebar
  refresh. Medians were **10.3/10.5 ms** and p95 **24.0/27.4 ms**. Both readers
  verified all 2,400 keys; source count/hash matched exactly. Source emitted
  51,800 lines / 3,439,297 bytes. Rendered load advanced 23,960/24,000 sequence
  positions across the two phases. Every measured API request passed 200 ms:
  browser maximum **126.7 ms**, server maximum **89.30 ms**. No long task,
  validation, clock, transport or request error. Artifacts:
  `/tmp/lab-output-typing-large-{browser,server}.json` and log.
- **Diagnostics:** same large fixture, 1,200 native keys, optional browser CPU,
  terminal I/O, coarse files, watchers and GC timings. **Five keys failed**,
  maxima **51.3/54.0 ms**. For key 57, 41.1 ms elapsed before its handler ran;
  CPU sampling mostly reported native `(program)` work. For key 117, the server
  sent its echo about 3.2 ms after input but browser observation was delayed to
  about 34.7 ms; no overlapping watcher/GC explains that interval. Keys 949/967
  overlapped producer batch writes of **29.22/29.92 ms** and **448/578 received
  frames** inside their latency windows. Source received these keys around
  30.7/30.6 ms after input even though server PTY input writes completed near
  the handler. These are distinct mechanisms, not proof of one global cause.
  Artifacts: `/tmp/lab-output-typing-diagnostic-{browser,server,cpu}.json` and log.

Producer input hashes and byte counts matched every native run; every owned
server stopped and terminal was removed. These are render callback measurements,
not physical display latency or measured iTerm parity. The overall latency goal
remains active. The next experiment targets available short PTY reads becoming
unnecessarily fragmented WebSocket output; browser stalls remain separate.
No main merge, push or live-server restart occurred. Main merge remains pending
after the earlier automatic approval rejection.

Validation: **35 focused tests passed** across the output fixture/readers,
existing quiet echo reader and server timing/owned-PID export tests. Coverage
includes exact suffix corruption/ahead/gap rejection, separate parse/render
continuity, partial frames, real PTY input retention and resize, minimum geometry,
producer metadata with/without input tracing, and CLI/browser fixture guards.
`node --check` and `git diff --check` passed.

### Follow-up experiment — available PTY reads (not retained)

A candidate drained available short reads until EAGAIN, bounded by 64 reads and
64 KiB per callback. Two real-pipe regression cases failed on the prior behavior
and passed on the candidate, verifying exact UTF-8/ANSI bytes, coalescing, EOF,
keyboard-reader cancellation and bounded callback work. The focused terminal,
connection and timing suite passed **77 tests**. Candidate and test are archived
at `/tmp/lab-pty-drain-rejected.patch` and `/tmp/lab-pty-drain-rejected-test.py`.

The matching 1,200-key diagnostic workload did **not** establish an improvement:
**16 keys failed** versus five in the preceding baseline diagnostic; maxima
were **61.7/60.8 ms**. All input and load validations passed, as did API budgets,
but source batch writes still reached **28.66 ms**. The quiet-output phase had
1,670 received frames versus 1,799, while the loaded phase had 9,325 versus
4,138. Both loaded phases generated 300 source batches / 714,300 source bytes.
The different number of tiny-frame bursts means these totals cannot be used as
a clean causal frame-reduction comparison. The production change and its tests
were removed; the implementation remains at the pre-experiment behavior.
Artifacts: `/tmp/lab-pty-drain-diagnostic-{browser,server,cpu,summary}.json`,
`/tmp/lab-output-typing-diagnostic-summary.json`, and the baseline/candidate test
logs. The candidate's owned terminal was removed and server stopped.

A further environment detail matters for the next comparison: the fixture's
fresh `LAB_HOME` has no tmux generation state, so `tmux_sockets.default_state()`
routes its uniquely owned sessions to the **default tmux server**. Its Lab
server/browser/configuration are disposable, but its tmux server is shared if
one already exists. This was also true of the earlier terminal measurements.
Do not call that transport fully isolated or attribute shared-server contention
to Lab without a controlled comparison. No other terminal or socket was changed.

Next: distinguish shared tmux scheduling from byte-pump and browser work, retain
normal/default-transport measurements, and add any fully owned transport test as
an explicitly separate diagnostic. Browser CPU `(program)` samples do not name
a cause; any new Chrome trace must check actual time coverage and preserve misses.

## 2026-09-23 — Separate transport effects and correct right-margin observation

The prior turn made progress by adding active-output coverage and rejecting an
ineffective PTY change. This follow-up retained that production implementation.

A fixed shared/private/private/shared sequence used 1,200 native keys per run,
5,000 mixed files, 2,500 Git changes, continuous output, 30 file updates, ordinary
polling and terminal I/O timing. Private runs used `TMUX_TMPDIR` under a newly
created `/tmp/lab-tmux-control-*` directory; the wrapper captured the private
socket inode and server PID, verified identity before cleanup, and never changed
ordinary/default-server sessions. Both private PIDs were confirmed gone afterward.

| Run | Keys ≥50 ms | Output maximum | Output + sidebar maximum | Loaded source batch-write maximum |
| --- | ---: | ---: | ---: | ---: |
| shared-a | 19 | 53.4 ms | 53.1 ms | 29.09 ms |
| private-b | 2 | 53.7 ms | 43.7 ms | 3.76 ms |
| private-b2 | 1 | 50.1 ms | 39.7 ms | 0.52 ms |
| shared-a2 | 9 | 47.4 ms | 71.0 ms | 32.17 ms |

All 4,800 characters matched source hashes and independent parse/render checks.
API maxima were below 200 ms in all four runs. Loaded received-frame counts were
16,230 / 1,795 / 1,795 / 11,186 respectively, for the same 300 source batches per
loaded phase. This associates bursts with the shared transport/environment;
it does not distinguish server contention from server configuration/state, or
justify changing the user's tmux routing. All failures remain retained. Artifacts:
`/tmp/lab-output-transport-{shared-a,private-b,private-b2,shared-a2}-{browser,server,transport,summary}.json`,
`/tmp/lab-output-transport-runs.json`, comparison JSON, logs and control wrapper.

An 800-key private diagnostic captured reduced Chrome timeline categories and a
CPU profile. Every key passed, maximum 49.4/43.8 ms. The 62,667-event trace covered
the workload and reported no data loss. It exposed a 10.03 ms callback at the
six-second Git decoration poll; the callback reapplies cached decorations before
checking freshness/fetching. Native `(program)` CPU samples in other windows
still do not establish a named browser cause. Artifacts:
`/tmp/lab-output-transport-private-trace-{browser,server,cpu,trace,transport,summary}.json`
and `...-trace.json.metadata.json`.

The terminal probe now accepts `LAB_PERF_TRACE_CATEGORIES`, records trace
start/end epochs and completion metadata, and saves independent CPU/trace
outputs even when the workload throws. Export happens once, closes trace streams
on read failure, reports diagnostic errors and retains successful sibling output.
Tests exercise normal export, one-export semantics, independent failures, stream
cleanup and the disabled path.

### A conservative overcount at the last column

At a full row, tmux may leave its cursor on the last occupied cell. The busy
footer's required `|` terminator can occupy that cell, but the probe read only
columns before the cursor. It therefore waited for later input despite the full
footer being present in a rendered row. The reader now includes the rightmost
cell only for the explicitly terminated output-footer protocol. Exact bytes,
source-offset continuity, no-ahead checks, cursor-row render gating and the
ordinary echo reader are retained. Regression coverage includes both boundaries
in a 49-column viewport, incomplete terminators and ahead-of-input rejection.

Native evidence with detailed tracing disabled confirms this case at input
lengths **2 and 51**, cursor column **48 of 49**, in both parse and render
observers. The two corrected runs retained all 2,400 keys apiece and all 60 file
updates; source hashes and rendered output coverage passed:

- Shared transport: **44 misses**, maxima **63.0/79.6 ms**; API maxima
  **74.0 ms** browser / **72.98 ms** server.
- Private transport: **one miss**, index 2358 at **54.3 ms**; maxima
  **46.6/54.3 ms**; API maxima **97.8/96.06 ms**.

These are new workloads, not replacements for failed earlier runs. Earlier
measurements at the full-row terminator boundary may overcount by one key
interval; other misses remain unexplained by that correction. Artifacts:
`/tmp/lab-output-transport-margin-{shared,private}-{browser,server,transport,summary}.json`
and `/tmp/lab-output-transport-margin-runs.json`. All fixture HTTP servers stopped,
owned sessions were removed and private tmux servers stopped. No main merge,
push or live-server restart occurred; the earlier merge rejection remains pending.

The updated diagnostic/echo/owned-export checks passed: **36 focused tests**
(within the subsequent 66-test sidebar/terminal run). Actual reduced-trace
coverage began 1,696.69 ms before the first measured key and ended 18.67 ms after
the last measured render. All private trace/margin PIDs were independently
confirmed gone and their sockets absent after cleanup.

## 2026-09-23 — Remove the Git timer's duplicate cached decoration pass

The six-second Git timer now calls `_sidebarGitStatusRefresh({repaint: false})`.
Mounted rows already display cached decorations; traversing every row again
before a freshness check/fetch duplicates work. Rebuild paths retain the helper's
default cached paint. Fresh server responses still decorate current rows once.
Polling cadence, five-second fetch floor, in-flight coalescing, failure behavior
and workspace/worktree ownership guards are unchanged.

A regression using the actual timer callback and refresh helper failed on the
prior code because it painted old status before fetching. It now checks live
fetching, overlapping ticks, no repeat paint with fresh cache, default paint for
rebuilt rows, updated response application, late response scope and inactive
views. **66 focused tests passed**, including native Chrome sidebar cache/Git
checks, sidebar configuration, output echo and diagnostics. The baseline failure
and candidate run are retained in `/tmp/lab-git-poll-{baseline-test,candidate-tests}.log`.

### Matching private-transport trace comparison

Both runs used the corrected probe, 800 native keys, scrolling output, 5,000 mixed
files, 2,500 Git changes and 20 document updates. Baseline supplied only
`lab-app.js` from `0217588`; the backend, workload and diagnostic settings matched.
Three measured Git timer callbacks changed from **13.268 / 7.688 / 9.447 ms**
to **0.179 / 0.013 / 0.035 ms**. This directly verifies removal of the duplicate
synchronous traversal without attributing unrelated whole-run variance to it.

Both runs retained every character and rendered ongoing output. All 800 keys in
each run passed 50 ms: baseline output/loaded maxima **45.3/39.0 ms**, candidate
**39.2/43.8 ms**. The loaded maximum increased, so this is not a claim of an
end-to-end improvement for every sample. API browser/server maxima were
**80.7/79.62 ms** before and **88.4/79.40 ms** after. Real Git checks passed.
Both traces covered the first input through last render, reported no data loss,
and saved complete CPU/trace diagnostics without errors. Both private server PIDs
were confirmed gone after cleanup.

Artifacts: `/tmp/lab-output-transport-git-poll-{before,after}-{browser,server,cpu,trace,transport,summary}.json`,
trace metadata, logs, `/tmp/lab-git-poll-comparison.json`, and the fixed control
wrapper/run manifest. Detailed tracing is disabled for the following final checks.

### Final fixed sequence with detailed diagnostics disabled

All four runs retained normal lifecycle/polling, 5,000 mixed files and 2,500 Git
changes per workspace. The three typing runs each retained 2,400 native keys,
independent parse/render verification and 60 real document updates. No run was
replaced to remove a failed result.

| Workload | UI / typing result | Browser API maximum | Server API maximum |
| --- | --- | ---: | ---: |
| Output, shared transport | 46/2,400 keys failed 50 ms; output/loaded maxima 50.5/72.1 ms | 115.2 ms (799) | 113.53 ms (831) |
| Output, private transport | 6/2,400 keys failed 50 ms; output/loaded maxima 54.2/52.4 ms | 152.1 ms (778) | 141.11 ms (809) |
| Ordinary echo, shared transport | all 2,400 passed; normal/loaded maxima 39.2/33.2 ms | 118.9 ms (776) | 112.51 ms (808) |
| Workspace/document navigation | all 80 clicks passed; workspace/document maxima 163.0/66.9 ms | 69.3 ms (654) | 67.76 ms (683) |

Request counts are in parentheses. All **3,007 browser** and **3,131 server**
request timings passed 200 ms. Ordinary echo included 87 parsed/86 rendered
reads after its initial marker scrolled away. Shared/private output sources
retained exact input hashes and wrote 51,440/51,360 lines. Both output phases
showed continuing valid rendered load. The output runs each completed 61
refreshes; ordinary echo completed 60. Real Git checks, native clocks, transport,
request, browser and input validation passed in every typing run. Navigation
validated 2,500 modified paths and 5,000 modified/5,000 clean rendered rows.

Source batch writes still reached **39.32 ms** shared and **23.07 ms** private,
so those pauses are not exclusive to a shared server. Both output runs had no
browser long task; ordinary echo had one while still passing every key. The
server/environment comparison is evidence for further investigation, not a
complete attribution of all stalls. The installed client and current shared
tmux server both report **3.6a**, ruling out that simple version mismatch.

All four HTTP servers stopped; all three owned terminals were removed. The
private socket was absent and its recorded PID independently confirmed gone.
No user terminal, main checkout, live server or default tmux configuration was
changed. Artifacts:
`/tmp/lab-output-transport-git-final-{shared,private,quiet,navigation}-{browser,server,transport}.json`,
typing summary JSONs, logs and `/tmp/lab-git-poll-final-runs.json`.
`node --check` and `git diff --check` passed.

The goal remains active: active-output typing misses, previously recorded IME
and cold-navigation outliers, unmeasured UI/API actions and physical/iTerm parity
remain unresolved. The Git timer change is a verified local reduction, not proof
that every action meets the overall budget. Main merge and push remain pending
after the earlier automatic approval rejection; no live-server restart occurred.

## 2026-09-23 — Reject an unhelpful PTY yield; sample the private producer

A candidate yielded one event-loop turn after receiving the first PTY chunk,
before collecting queued fragments for a WebSocket frame. It preserved the
incremental UTF-8 decoder and EOF/send-failure cleanup. Four real-pipe tests
split ASCII or UTF-8/ANSI data into four-byte reads, required exact output and
verified cleanup. The unmodified implementation failed the two coalescing
assertions; the candidate passed **79 focused tests**, including document
terminal connections, WebSocket reliability and server timing instrumentation.

The fixed native sequence used 1,200 keys per run, scrolling output, 5,000 mixed
files, 2,500 Git changes, sidebar updates and terminal-boundary diagnostics.
It ran baseline shared/private, then candidate shared/private; this was not an
ABBA comparison. All runs and misses were retained.

| Code / transport | Failed keys (>50 ms) | Output median / p95 / max | Loaded median / p95 / max |
| --- | ---: | ---: | ---: |
| Baseline / shared | 2 | 11.3 / 25.8 / 55.3 ms | 19.6 / 29.7 / 48.1 ms |
| Baseline / private | 1 | 5.8 / 28.1 / 43.0 ms | 7.4 / 26.5 / 51.5 ms |
| Yield / shared | 2 | 11.0 / 22.3 / 46.2 ms | 13.0 / 27.0 / 61.4 ms |
| Yield / private | 4 | 8.6 / 29.2 / 58.2 ms | 8.9 / 27.1 / 50.2 ms |

The largest frame increased from 1,024 to 2,048 characters and tiny-frame counts
fell, but this did not establish a typing-latency improvement. Producer writes
still reached 21.65 ms in the candidate's private run. The candidate and its
tests were removed; production returned exactly to `04620e7`. Their patch/test
are archived in `/tmp/lab-pty-yield-candidate.patch` and
`/tmp/lab-pty-yield-candidate-test.py`, with baseline/candidate test logs.

All 4,800 keys passed exact source hashes and independent parse/render checks;
Git and API validation passed. Browser/server API maxima were 134.5/127.85 ms,
83.0/73.34 ms, 77.6/74.06 ms and 135.1/133.70 ms, respectively. Each run had one
browser terminal socket and one server connection. Geometry remained 49 columns
by 48 xterm rows / 47 producer rows, with only startup resize messages. Total
repaint bytes varied despite the same generated load; frame counts alone cannot
establish an end-to-end improvement. HTTP servers stopped, private PIDs were
independently confirmed gone and private sockets were removed.

Artifacts: `/tmp/lab-output-transport-yield-{before,after}-{shared,private}-{browser,server,transport,summary}.json`,
logs, `/tmp/lab-pty-yield-{before,after}-runs.json`, and
`/tmp/lab-pty-yield-comparison.json`.

### Private process sampling is diagnostic evidence

With unmodified `04620e7`, an owned private server and its single owned Python
output producer were sampled for 15 seconds at 2 ms intervals. The wrapper
checked the private socket inode/server PID and uniquely identified the
`lab-navigation-` Python pane before sampling. Both samplers exited normally;
both process PIDs were independently confirmed gone after normal fixture
cleanup, and the socket was absent. No shared/user tmux process was sampled.

The native run retained all 1,600 keys, exact source hash, 40 updates/refreshes,
ongoing rendered output and valid Git state. Seven keys missed 50 ms, with
output/loaded maxima 57.2/34.3 ms. Browser/server API maxima were
100.5/89.95 ms (580/611 requests). This instrumented run is not a final latency
result: native sampling can perturb scheduling.

During the sampled window, 10 of 300 producer batches spent more than 10 ms in
their writes; the maximum was 23.47 ms. Five of the seven slow keys fell within
that window. Across all seven slow keys, producer input was read 21.88–26.17 ms
after the measured key start, following a batch write of 19.50–23.47 ms. The
corresponding input-to-render windows contained 256–282 PTY reads and 256–282
WebSocket sends. This establishes overlap, not a complete causal attribution.

The aggregate tmux sample spent 5,765 of 5,990 main-thread samples in `select`;
the producer spent 5,843 of 6,010 in `select` and 98 in the system write path.
These aggregates do not distinguish healthy waiting from a scheduling problem
and cannot explain an individual stall by themselves. The tmux 3.6a Darwin
implementation explicitly selects this event backend; its presence is not
evidence of the unrelated newer-version spin report.
[tmux 3.6a Darwin implementation](https://raw.githubusercontent.com/tmux/tmux/3.6a/osdep-darwin.c).
Kernel watermarks depend on terminal speed in the XNU source, but no terminal
speed, tmux configuration or kernel setting was changed and no benefit from
such a change is established.
[XNU tty implementation](https://raw.githubusercontent.com/apple-oss-distributions/xnu/main/bsd/kern/tty.c).

Artifacts: `/tmp/lab-output-transport-sample-private-{browser,server,transport,summary}.json`,
`/tmp/lab-output-transport-sample-private-{tmux,producer}-sample.txt`, its log,
and `/tmp/lab-pty-sample-runs.json`.

### Reject a one-millisecond burst frame interval

A second candidate sent the first/idle chunk immediately, then waited only for
the remainder of a one-millisecond interval after the preceding send. The fd
reader continued collecting bytes during that wait. It did not drop output,
alter input cadence, change terminal settings or change the fixture workload.
The final **83 focused tests passed**. Real-pipe tests additionally checked that
post-idle output had no added wait, burst waits requested at most one millisecond,
split UTF-8/ANSI data survived, and EOF/disconnect cleanup remained intact.

A fresh fixed sequence again measured baseline shared/private followed by
candidate shared/private, 1,200 keys each. This order is not ABBA, and the
differences are not sufficient to attribute every change to the candidate.

| Code / transport | Failed keys (>50 ms) | Output median / p95 / max | Loaded median / p95 / max |
| --- | ---: | ---: | ---: |
| Baseline / shared | 0 | 11.2 / 21.8 / 47.0 ms | 19.3 / 28.8 / 49.8 ms |
| Baseline / private | 3 | 7.4 / 27.1 / 51.8 ms | 11.8 / 27.2 / 38.3 ms |
| Interval / shared | 15 | 14.0 / 38.3 / 75.7 ms | 10.1 / 29.6 / 47.9 ms |
| Interval / private | 0 | 15.7 / 26.2 / 45.9 ms | 15.8 / 26.9 / 38.3 ms |

Tiny frames fell again, but producer write stalls remained and the shared
candidate's maximum reached 75.7 ms. Its source writes reached 30.41 ms, compared
with 1.10 ms for this shared baseline. Private medians increased even though
its failed-key count decreased. These mixed results do not justify a production
delay. The patch and tests were removed, restoring the production file exactly
to `04620e7`; this checkpoint records diagnostics only.

All 4,800 keys passed exact source hash and independent parse/render checks.
Each run completed 30 document updates and 30 or 31 refreshes; ongoing rendered
output, real Git state, native clocks and transport checks passed. Browser/server
API maxima were 79.6/72.59 ms, 116.5/114.77 ms, 82.7/81.78 ms and 134.1/132.15 ms.
All four HTTP servers stopped. Both private server PIDs were independently
confirmed gone and their sockets absent.

Artifacts: `/tmp/lab-output-transport-batch-{before,after}-{shared,private}-{browser,server,transport,summary}.json`,
logs, `/tmp/lab-pty-batch-{before,after}-runs.json`,
`/tmp/lab-pty-batch-comparison.json`, `/tmp/lab-pty-batch-final-tests.log`,
and the rejected `/tmp/lab-pty-batch-rejected.patch` / test archive.
No production timing, buffering or tmux configuration change remains.

## 2026-09-23 — Isolate producer stalls before the browser boundary

A component control uses the existing scrolling-output producer directly under
a PTY, or inside a newly created private tmux server attached through a PTY.
Both paths retain 49×47 producer geometry, 40 colored lines per 50 ms, the exact
LCG input and a 25 ms send schedule. The controller drains output and records
source batch writes and input receipt. It verifies every input hash and byte
count; direct PTY received-byte counts must also match all source writes.

This is explicitly a transport diagnostic, not a UI or iTerm latency result:
it has no WebSocket, browser rendering, Lab polling or Git workload. It does not
answer terminal capability queries as xterm does. It uses private tmux's loaded
configuration rather than applying Lab's session-specific wheel settings. The
same generated producer function is used, but its marker is a hyphenated UUID.
These differences prevent substituting its results for the native browser
workload or attributing every browser miss to tmux.

An initial four-run smoke used `select` for controller readiness and exposed up
to 10.10 ms of input-schedule lateness. It is retained separately in
`/tmp/lab-pty-boundary-smoke.json`. The extended fixed A/B/B/A sequence uses the
platform's default selector (kqueue here), keeping actual send times and all
schedule lateness. Each run retains 600 inputs and 302 source batches.

| Path | Batch write median / p95 / max | Batches >10 ms | Input send → source read p95 / max | PTY reads |
| --- | ---: | ---: | ---: | ---: |
| Direct A1 | 0.086 / 0.132 / 0.279 ms | 0 | 0.093 / 2.989 ms | 1,505 |
| Private tmux B1 | 0.235 / 12.638 / 15.531 ms | 75 | 12.305 / 15.633 ms | 76,485 |
| Private tmux B2 | 0.228 / 12.219 / 12.959 ms | 39 | 11.861 / 13.079 ms | 40,521 |
| Direct A2 | 0.085 / 0.136 / 0.346 ms | 0 | 0.085 / 2.944 ms | 1,505 |

All 2,400 input characters matched. Both direct runs received exactly 792,117
source bytes; tmux repaint output differed as expected. Maximum controller
schedule lateness was 2.18 ms. Every owned producer/attach/server PID was checked
gone after cleanup; private socket identity was checked before removal. No user
server/session was sampled, reconfigured or stopped. Long source writes can
therefore occur in this component path without browser or WebSocket work.
The observation narrows the investigation; it does not identify the exact
tmux/kernel mechanism or prove the browser contributes no additional delay.

Artifacts: `/tmp/lab-pty-boundary-control.py`, `/tmp/lab-pty-boundary-abba.json`,
and each recorded run directory's producer/transport JSON and received bytes.

### Attachment speed control did not establish a fix

XNU derives tty buffer watermarks from output speed, within fixed bounds.
[XNU tty implementation](https://raw.githubusercontent.com/apple-oss-distributions/xnu/main/bsd/kern/tty.c),
[XNU tty bounds](https://raw.githubusercontent.com/apple-oss-distributions/xnu/main/bsd/sys/tty.h).
A separate owned-only A/B/B/A control changed the attachment PTY from its
observed 9,600 baud default to 115,200 before `tmux attach` executed. The producer
pane stayed at 9,600 in every run; both speeds were read back. Nothing changed
on a user pane, the default server or the production attachment path.

For 600 inputs / 302 batches per run, default/high/high/default batch-write p95
was **12.47 / 12.52 / 12.50 / 12.41 ms**; maxima were
**16.90 / 15.36 / 13.97 / 16.06 ms**. Counts above 10 ms were
**65 / 86 / 66 / 58**. Every input hash and geometry check passed, all owned PIDs
were independently confirmed gone and private sockets were absent. This
does not support changing the attachment speed. Source settings remain outside
this comparison, and the component still lacks xterm capability negotiation.
Artifacts: `/tmp/lab-pty-speed-control.py`,
`/tmp/lab-pty-boundary-speed-abba.json` and its recorded per-run directories.

### Optional source CPU diagnostics

`--trace-terminal` output typing now records same-thread CPU time around each
whole source batch write and input-footer write. It adds no per-syscall tracing.
With diagnostics disabled there are no CPU clock calls or added CPU fields.
These synchronous intervals can distinguish producer computation from waiting;
they do not by themselves identify which downstream process causes waiting.

**36 focused tests passed** for output typing, exact echo readers, diagnostic
exports and server timing. Real PTY tests retain resize, source byte/hash and
live-after-report guarantees. They validate traced CPU intervals and run the
untraced producer with a CPU clock that raises if called. The log is
`/tmp/lab-output-cpu-tests.log`.

The direct/attachment-speed controls above used the producer from `f059707`,
before adding these CPU fields; their full generated programs are retained.
The following native runs use the new diagnostics and the unchanged production
code, normal polling, 5,000 mixed files, 2,500 Git changes and 30 updates each.

| Transport | Failed keys (>50 ms) | Output / loaded maximum | Browser / server API maximum |
| --- | ---: | ---: | ---: |
| Shared | 19/1,200 | 61.2 / 75.7 ms | 87.7 / 76.77 ms (419/450 requests) |
| Private | 3/1,200 | 54.6 / 40.1 ms | 135.1 / 133.43 ms (395/433 requests) |

All 2,400 characters passed source hash and independent parse/render checks.
Both phases retained advancing rendered output, each run completed 31 sidebar
refreshes, and Git/clock/transport checks passed. There were no browser long
tasks. Both HTTP servers stopped, the private server PID was independently
confirmed gone and its socket absent. These are diagnostic runs, not a passing
final typing result; all 22 misses remain reported.

The shared source had 34 batches exceeding 10 ms, using only
0.017–0.050 ms of source-thread CPU apiece. Its longest write took **35.057 ms**
with **0.037 ms CPU**. The private source had 21 such batches, using
0.018–0.098 ms CPU; its longest took **22.398 ms** with **0.098 ms CPU**.
Most elapsed time is therefore not producer computation. The three private
misses read their input 22.50–24.40 ms after the measured start and spent only
0.018–0.019 ms CPU building/writing their footer. Other shared misses also
include browser queueing or delays after the source read, so this does not
assign every stage of the input-to-render budget to one cause.

Artifacts: `/tmp/lab-output-transport-source-cpu-{shared,private}-{browser,server,transport,summary}.json`,
logs, `/tmp/lab-source-cpu-runs.json` and `/tmp/lab-source-cpu-comparison.json`.

### Source speed control also did not establish a fix

The complementary component A/B/B/A sequence changed only its owned producer
pane to 115,200; its attachment stayed at 9,600. Every setting was read back.
It used the new CPU-instrumented producer in all four runs, each with 600 exact
inputs and 302 batches. Default/high/high/default write p95 was
**12.56 / 12.41 / 12.45 / 12.75 ms**, maxima
**13.46 / 15.80 / 12.99 / 13.86 ms**, and batches above 10 ms
**99 / 101 / 95 / 92**. This also provides no basis for changing production tty
speed. Every input/geometry check passed and owned resources were cleaned up.
Artifacts: `/tmp/lab-pty-source-speed-control.py`,
`/tmp/lab-pty-boundary-source-speed-abba.json` and its per-run directories.

The retained change is optional measurement support only. No production
buffering, baud rate, tmux configuration or session behavior changed. Active
output typing, earlier IME/cold-navigation outliers, remaining UI/API coverage
and physical/iTerm parity still require work. Main merge remains pending after
the earlier automatic approval rejection; no main merge, push or live restart
was attempted.


## Visible terminal initialization and native creation coverage — 2026-09-23

Added `--terminal-create` to the isolated native navigation runner. It clicks
**New → Terminal**, waits for the new session's exact echo marker in an actual
xterm render, then sends and verifies a native key. Every creation checks unique
live/saved identities, the owning workspace, focus, selected tab, open socket,
one visible pane, and the three-parked-plus-one-active resource bounds. The
fixture uses a configured owned echo shell and the ordinary creation endpoint;
it does not measure user login scripts or provider startup. Initial workspace
and picker clicks remain separate timed actions, and no first samples are
removed. Normal server lifespan, polling and the default tmux generation remain.
Cleanup disables only fixture autospawn, verifies owned name/cwd/command/PID,
purges through the normal API, checks exact live names and saved entries, and
restores the fixture process's prior SHELL environment.

The new workload exposed a consistent miss. With 5,000 mixed flat files and
2,500 real Git changes per workspace, all 20 original creations exceeded
200 ms. The retained production change moves `_termShowPane(myContainer)` just
before `termXterm.open(myContainer)`. xterm can measure its font during open;
the existing fit, valid-dimension guard, retry fallback, and WebSocket ordering
remain. Pane switching, focus scheduling, parked retention, and GPU ownership
are unchanged.

### Measured creation results

Every row below includes 20 creations plus 20 picker clicks and one workspace
click. These runs have no detailed Chrome tracing:

| Run | Creation first/max | Creation median | Creation p95 | Creation misses >200 ms |
| --- | ---: | ---: | ---: | ---: |
| Original baseline | 348.6 ms | 221.5 ms | 266.1 ms | 20/20 |
| Visible initialization | 288.4 ms | 200.7 ms | 235.4 ms | 10/20 |
| Baseline repeated from HEAD | 298.7 ms | 230.4 ms | 248.2 ms | 19/20 |
| Visible initialization repeated | 283.4 ms | 201.3 ms | 209.6 ms | 12/20 |

The last run also retained a **203.3 ms workspace click**. Picker maxima were
50.1/55.0/56.5/53.1 ms. All 1,207 browser and 1,411 server request records across
these four runs stayed under 200 ms; largest browser/server durations were
160.2/159.13 ms. All functional/input/clock/resource checks passed. This is a
repeatable partial improvement, not completion of the creation budget.

The original baseline and the rejected containment run below reported cleanup
failure for `bash-2` even though all owned processes exited. The fixture had
used tmux `has-session`, which also matches prefixes: after deleting `bash-2`,
its check found `bash-20`. Cleanup now uses the normal exact-name listing
helper. A regression test retains both names and exercises this case, failure
cleanup, environment restoration and preservation of foreign sessions. The
subsequent baseline and both visible-initialization runs reported successful
cleanup; all recorded producer PIDs were independently checked absent.

Artifacts: `/tmp/lab-terminal-create-{before,visible-open,visible-control,visible-repeat}-{browser,server}.json`,
associated logs, and `/tmp/lab-terminal-creation-comparison.json`.
A final read-only tmux listing found none of the 113 exact owned names from
the comparison, diagnostic, tab and typing runs still present; see
`/tmp/lab-terminal-creation-cleanup.json`.

### Why visibility matters

Separate six-creation diagnostics show **six 50 ms retry timers before, zero
after**. All six original timer callbacks map to the `_openWS` geometry retry
in lab-app.js; actual delays were 52.59, 73.58, 50.54, 50.05, 50.17 and 51.21 ms.
Both traces cover the first measured click through the final verified native
key render, with no reported data loss. The later snapshot can include a
cursor repaint after profiling stopped; coverage uses the per-action verified
render, not that later snapshot. A real-Chrome regression check executes the
actual fresh-pane initialization fragment with vendored xterm and FitAddon at
three pane sizes. It proves valid, fitted initial geometry before connection,
correct Unicode output and focus. The same check fails on the unchanged HEAD
source because its initial dimensions require a later font measurement frame.

The CPU profiles do **not** show lower glyph-measurement CPU: sampled `_measure`
time was 229.73 ms before and 240.98 ms after. This change removes an avoidable
connection delay, rather than establishing that glyph layout became cheaper.
Diagnostic timings are retained separately from the untraced comparison.

Artifacts: `/tmp/lab-terminal-create-{diagnostic,visible-diagnostic}-{browser,server}.json`,
`/tmp/lab-terminal-create{,-visible}-trace.json` and metadata,
`/tmp/lab-terminal-create{,-visible}-cpu.json`, and
`/tmp/lab-terminal-create-trace-comparison.json`.

### Rejected width-container experiment

An earlier candidate applied strict CSS containment only to xterm 5.3's
body-mounted glyph measurement box, including after WebGL disposal. It passed
108 focused checks, including equal real-Chrome glyph widths across fonts,
sizes, weights/styles and Unicode, equal rendered rows, renderer fallback and
disposal. However, the 20-creation run still missed 19/20: median 219.1 ms,
p95 251.6 ms, first/max 400.5 ms. It provided no material overall improvement
against the original baseline and was fully removed, including its test-only
helper changes. No vendor asset was edited.
Artifacts: `/tmp/lab-terminal-width-containment-rejected.patch`,
`/tmp/lab-terminal-width-containment-tests-2.log`, and
`/tmp/lab-terminal-create-contained-{browser,server}.json` plus its log.

### Functional and latency checks

- **120 distinct focused checks passed**: terminal UI, resources, lifecycle,
  WebSocket behavior, native tab probe and creation fixture guards. The first
  119 passed together; the additional geometry test and both existing lifecycle
  checks then passed together. The original-code geometry failure was reproduced
  separately. Node syntax and `git diff --check` passed. This does not replace
  the earlier broad suite's two known baseline failures.
- Native terminal tab workload: **68/68 actions below 200 ms**, including six
  first selections, 30 warm switches and 30 cycles beyond retained panes.
  Workspace max 148.3 ms; first selections 123.1 ms; mounted 52.9 ms; warm
  90.1 ms; cycle/eviction 129.1 ms. Exact echoed input survived replay, focus and
  pane bounds passed, zero browser errors, and all 67 browser/105 server API
  records passed (max 60.3/58.45 ms). All six owned sessions were removed.
- Native scrolling-output typing: **1,200 exact keys**, 600 per phase, with
  30 real file updates and 31 sidebar refreshes. All producer hash, parsed/rendered
  continuity, rendered output, Git and timestamp checks passed. Output-only
  median/p95/max was 13.2/41.7/62.6 ms with **four >50 ms misses**; output plus
  sidebar updates was 10.9/27.1/37.6 ms, with none. There were no Long Tasks or
  browser errors, and all 409 browser/441 server API records passed (max
  119.4/117.46 ms). The owned session was purged and fixture server stopped.
  This is a functional recheck with retained latency failures, not evidence of
  a steady-state typing improvement or physical/iTerm parity.

Artifacts: `/tmp/lab-terminal-visible-final-tests.log`,
`/tmp/lab-terminal-visible-geometry-tests.log`,
`/tmp/lab-terminal-create-visible-{tabs,output}-{browser,server}.json`, logs and
`/tmp/lab-terminal-create-visible-output-summary.json`.

Terminal creation, output typing, the retained workspace/IME/cold-navigation
outliers, remaining action/endpoint coverage and physical/iTerm comparison
still need work. Main merge remains pending after the prior automatic approval
rejection. No merge, push or live-server restart was attempted.


## Batch tmux setup without dropping failure recovery — 2026-09-23

The next measured portion of terminal creation was
`_configure_tmux_wheel_scrolling`: four serial tmux client processes for mouse
mode, alternate-screen behavior, WheelUpPane routing and WheelDownPane cleanup.
A fresh 20-creation baseline spent a median **30.60 ms** in this helper.

The helper now sends the same four commands, in the same order and on the same
socket, in one tmux command sequence. The environment, option values and exact
wheel condition remain unchanged. A failed sequence retries all four idempotent
commands individually so a missing/exited session or failed option does not
prevent later binding cleanup. This matters because tmux stops the remainder
of a semicolon-separated sequence after an error; the
[tmux 3.6a manual](https://raw.githubusercontent.com/tmux/tmux/3.6a/tmux.1)
documents that behavior in Parsing Syntax. The native failure test confirms it
on the installed tmux. The failure path can make five client calls instead of
four; the successful creation path makes one.

### Matched native comparison

Both runs used 20 ordinary New/Terminal creations in the same 5,000-file,
2,500-Git-change-per-workspace fixture, retaining every first sample and normal
polling. Both enabled only the same coarse session-function diagnostics.

| Measurement | Before | Batched setup |
| --- | ---: | ---: |
| Wheel setup median / maximum | 30.60 / 36.59 ms | 8.21 / 18.64 ms |
| Creation endpoint median / maximum | 66.13 / 88.04 ms | 45.07 / 63.94 ms |
| Creation click median / p95 | 204.8 / 236.1 ms | 188.3 / 218.6 ms |
| Creation click first / maximum | 316.7 ms | 285.1 ms |
| Creation clicks above 200 ms | 11/20 | 4/20 |

A longer run **without function tracing** retained all 40 creations, all
40 picker clicks, and its initial workspace click. Creation median/p95/max
was **183.7 / 208.4 / 298.2 ms**, with **7/40 misses above 200 ms**; first
creation was also the maximum. Picker maximum was 57.0 ms, and the workspace
click was 198.2 ms. The creation endpoint median/max was 52.53/68.20 ms.
These results show a partial improvement, with cold startup and some subsequent
creations still outside the goal.

Across all three runs, all **1,124 browser and 1,297 server API records** stayed
below 200 ms (maximum 156.9/155.47 ms). There were no browser/request errors.
All 80 creations passed unique live/saved identity, workspace isolation,
selected/focused/open-socket state, actual rendered marker plus native-key
verification, input-clock checks and the three-parked-plus-one-active pane
bounds. Each fixture reported cleanup complete and server stopped; all 80
recorded producer PIDs were independently checked absent. A final read-only
tmux listing also found none of the 80 exact owned names still present.

### Correctness checks

**110 focused tests passed** across terminal routes and the new real-tmux
integration check. The integration check uses its own temporary TMUX_TMPDIR,
private socket and empty configuration. It verifies the exact wheel binding,
no root WheelDownPane override, mouse/alternate-screen settings only on the
intended session, and correct global bindings even when the target session is
missing. Both default and named-socket fallback are covered separately. The
private native test was rerun after adding an explicit check that its owned
server PID exits; it passed. `git diff --check` passed. The earlier broad
suite's two known baseline failures remain separate from these focused checks.

Artifacts: `/tmp/lab-terminal-create-tmux-batch-{before,after,final}-{browser,server}.json`,
associated logs, `/tmp/lab-terminal-tmux-batch-comparison.json`,
`/tmp/lab-terminal-tmux-batch-tests.log`, and
`/tmp/lab-terminal-tmux-batch-native-final.log`.

This checkpoint changes session setup only. It does not establish a steady-state
typing improvement. Cold creation, remaining creation misses, previously retained
output-typing/IME/navigation failures, complete action/endpoint coverage and
physical/iTerm parity still require work. Main merge remains pending after the
prior automatic approval rejection; no merge, push or live restart was attempted.


## Keep final renderer geometry before connecting — 2026-09-23

Investigated the remaining first-creation delay after `4c416e3`. Two frontend
candidates were tested and **fully removed**. Production lab-app.js was restored
byte-for-byte to that checkpoint. The retained change strengthens the native
geometry regression check to exercise both real WebGL and DOM rendering.

### Asset intent and parallel loading did not establish an end-to-end gain

An earlier diagnostic placed the normal sequential terminal asset requests
between approximately +118.5 and +148.3 ms after the first Terminal click.
A candidate combined parallel ordered script loading with download hints when
New opens. Attachment still waited for all scripts, and the menu still waited
for its captured agent policy and rejected stale scope changes.

The first hint implementation used `rel=preload`. A private real-Chrome HTTP
fixture returned a non-cacheable 503 to the hint, then would serve the normal
script successfully. Chrome reused the failed preload response, so attachment
still failed. **Two checks passed and the failed-hint check failed**; this
implementation was rejected. An alternative `rel=prefetch` passed that recovery
case, kept hints out of the load-promise cache, did not execute scripts early,
and reused successful downloads. Tests also forced addon responses to finish
before the core script, confirmed ordered execution and no duplicate requests,
and exercised direct loading without hints. That candidate passed **104 focused
checks**, including Home, document-terminal and lifecycle behavior.

It nevertheless did not establish a latency benefit in the 5,000-file/2,500-Git-
change fixture. All first samples remained in the comparison:

| Untraced 20-creation run | First / maximum | Median | p95 | Misses >200 ms |
| --- | ---: | ---: | ---: | ---: |
| Prefetch plus parallel scripts | 351.1 ms | 189.3 ms | 230.0 ms | 7/20 |
| Fresh unchanged frontend control | 274.1 ms | 186.0 ms | 229.4 ms | 3/20 |

Picker maxima were 52.4 and 47.7 ms. The first creation's preceding API work was
also slower in the candidate run, so these runs do not establish that hints
caused all of the difference. They provide no end-to-end improvement to retain.

A separate six-creation trace confirmed the hints downloaded roughly 197 ms
before the first Terminal click and that subsequent script loads used cached
responses (`fromCache: true`, zero transferred body bytes for xterm). Those
later resource events still span about +83.5 to +93.0 ms after the click. The
trace covers the first measured click through the last verified native-key
render, with about 101 ms remaining afterward and no reported data loss.
Diagnostic creation median/max was 214.4/250.9 ms, with five misses; it is not
an untraced performance comparison. Both the hints and parallel-loader change
were removed together; this does not separately establish the effect of either
component on every entry path.

Artifacts: `/tmp/lab-terminal-{preload,prefetch}-rejected.patch`, their paired
`-rejected-test.py` archives, `/tmp/lab-terminal-assets-tests.log`,
`/tmp/lab-terminal-assets-prefetch-tests.log`, `/tmp/lab-terminal-assets-final-tests.log`,
`/tmp/lab-terminal-create-prefetch-{first,control,diagnostic}-{browser,server}.json`,
associated logs, and `/tmp/lab-terminal-create-prefetch-{trace,cpu}.json` plus
trace metadata.

### Earlier connection fails the final-grid invariant

A second candidate started `_openWS(true)` after the initial fit but before
`_termEnableWebgl()`, aiming to overlap the independent socket/PTY handshake
with synchronous GPU setup. Its 20-creation median was **185.8 ms**, p95
221.6 ms, first/max 289.6 ms, with **5/20 misses**. Against the unchanged control's
186.0 ms median, this provided no meaningful gain. The original 106 focused
checks passed, but did not compare the initial connection against real GPU
geometry.

Inspection of the vendored renderers revealed an important difference: the
DOM renderer derives cell width from the fractional measured character width,
whereas the WebGL renderer floors the device character width. The final fitted
column count can therefore change when enabling WebGL. The expanded native
check executes the actual fresh-pane block with real xterm, FitAddon and the
WebGL addon, records the grid at the connection boundary, and compares it with
the active renderer's proposed grid. **The early-connection candidate failed
this check with real WebGL** while the DOM variant and prior lifecycle checks
passed. Connecting early would reintroduce the wrong-grid/reflow behavior that
fit-before-WebSocket was meant to avoid.

After restoring the existing order—visible open, initial fit, WebGL enable,
clear, and final fit inside `_openWS`—**107 focused tests passed**. The geometry
check covers both renderers at three pane sizes, correct Unicode buffer content,
focus and safe disposal. The existing valid-size retry remains. The GPU test
uses an owned Chrome profile with GPU enabled and requires a real loaded addon;
the DOM case remains explicitly separate. No vendor asset or production startup
order changed in this checkpoint.

Artifacts: `/tmp/lab-terminal-connect-before-gpu-rejected.patch`,
`/tmp/lab-terminal-create-connect-first-{browser,server}.json`, its log,
`/tmp/lab-terminal-connect-before-gpu-tests.log`,
`/tmp/lab-terminal-connect-gpu-geometry-rejected-tests.log`, and
`/tmp/lab-terminal-gpu-geometry-final-tests.log`.

### Coverage and remaining work

Across these four native runs, all **969 browser and 1,158 server API records**
stayed under 200 ms (maxima 148.0/121.91 ms). There were no browser or request
errors. All 66 created terminals passed the existing rendered-marker/native-key,
unique live/saved identity, workspace, focus, input-clock and pane-bound checks.
All fixtures reported successful cleanup and stopped servers; all 66 recorded
producer PIDs were independently checked absent. A final read-only tmux listing
also confirmed none of the 66 exact owned names remained. The API timing success and
short echo checks did not prove initial renderer geometry, which is why the
new native guard was necessary. Summary:
`/tmp/lab-terminal-startup-candidates-comparison.json`.

This is a correctness/diagnostic checkpoint, not a new speed improvement.
Cold creation and remaining creation misses still need work, alongside the
previously retained output-typing, IME and navigation failures, remaining UI/API
coverage, and physical/iTerm parity. The next optimization must preserve final
renderer geometry; it can instead examine work awaited before attachment, such
as the confirmed-created row followed by autospawn persistence and a fresh
session-list request. Main merge remains pending after the prior automatic
approval rejection. No merge, push or live restart was attempted.


## Attach confirmed terminal rows while refreshing metadata — 2026-09-23

Session creation previously awaited both autospawn persistence and a fresh
session-list GET before starting attachment. The POST already persists the
session and returns its identity, kind, cwd, command and linked metadata.
The retained change still waits for autospawn persistence, then seeds the
owning cache from that confirmed response and starts the existing attachment
path while the fresh GET reconciles metadata. It does not add an initial
pill repaint; the normal refresh and connection renders supply the UI update.
The renderer/fit/WebSocket order, asset loader and backend are unchanged.

### Preserve asynchronous ownership and recovery

Per-workspace/vault list versions prevent reads started before confirmed
creation from removing its row while assets load. Explicit current-tab,
selected-tabs and kill-all close intent also advances the version, so the
creation refresh cannot bring back a tab the user subsequently closed.
A delayed refresh never attaches again or overrides a later selection.
Captured vault/workspace and Home association behavior remain in place.

Two regression checks exposed problems in intermediate candidates:

- The initial overlap candidate could restore a ghost pill after the newly
  usable terminal was closed while its GET was pending. The actual close
  handler reproduced this failure. Versions now invalidate that older read
  and its fallback; tests cover all three close paths, with stale responses
  both containing and omitting the closed row.
- Merging a missing created row only in the caller after awaiting refresh was
  too late. The actual attachment preamble, with a deferred asset promise,
  could resume between the empty-list publication and the caller's next
  microtask, fail membership validation and cancel attachment. Both ordinary
  workspace and Home checks failed. The fallback now joins the same refresh
  publication as the fresh list, including failed reads after another metadata
  update invalidates the warm cache. Fresh enrichment still takes precedence.

The final focused set passed **150 tests** across creation, Home, document
terminals, close/multiselect actions, resources, lifecycle and WebSocket client
recovery. It includes real DOM and WebGL connection-geometry checks. Earlier
stages recorded 134 passes, then 27 passes/one close-race failure, 144 passes
after close ownership, two asset-boundary failures, and 146 passes after atomic
publication. Four additional failed-read/cache-invalidation cases bring the
final total to 150. These failures were fixed, not excluded from the record.
`git diff --check` passed. The older broad suite's known baseline failures
remain separate; this checkpoint does not claim a new fully green broad run.

### Native creation comparison

All runs used the same untraced 5,000-file, 2,500-Git-change fixture and ordinary
New/Terminal clicks through first rendered output, followed by an exact native
key echo and saved-identity verification. All first samples remain included.
Controls served the frontend from `aa862c3`; all used the unchanged current
backend. The configured owned echo shell isolates Lab creation, not arbitrary
user shell scripts or agent startup.

| Run | Creations | First / max | Median | p95 | Creation misses >200 ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| Unchanged control (`before`) | 20 | 317.5 ms | 171.7 ms | 196.6 ms | 1 |
| Initial overlap, extra repaint (`after`) | 20 | 287.6 ms | 172.1 ms | 193.8 ms | 1 |
| Overlap without extra repaint (`once`) | 20 | 268.0 ms | 164.9 ms | 184.5 ms | 1 |
| Repeated unchanged control (`control`) | 20 | 299.9 ms | 192.0 ms | 218.7 ms | 9 |
| Close/atomic-publication guards (`final`) | 40 | 316.8 ms | 166.2 ms | 181.1 ms | 1 |
| Completed failed-cache fallback (`verified`) | 20 | 297.6 ms | 172.3 ms | 193.0 ms | 1 |

The last 60 creations had **58/60 under 200 ms**; both misses were first cold
creations. Control medians ranged from 171.7 to 192.0 ms, so the full difference
from the slower control should not be attributed to this frontend change.
Creation POST medians also varied: 38.53/58.39 ms in controls versus 48.36/51.42 ms
in the last two runs. No cold-start improvement is established by these runs.
The initial extra-repaint candidate did not improve the first control's median
and its duplicate publication was removed.

Existing native timing records corroborate the overlap: in 56 of 58 final
creation rows with an unambiguous POST/GET pair, pane construction began before
the list response completed, versus zero of 39 such control rows. Rows with
additional session requests were omitted only from that component classification;
all their latency and functional results remain in the table.

Picker maxima across creation runs were 47.3–54.6 ms. The `once` run also had a
**216.1 ms workspace-opening miss**, retained separately from its creation miss.
The other five workspace-opening samples were 145.7–166.8 ms. The last 40- and
20-creation runs opened the workspace in 157.3 and 147.9 ms.

### Functional recheck and cleanup

A separate native terminal-tab run passed all **68 actions under 200 ms**:
workspace opening 178.9 ms, first/cold terminal switching maximum 125.0 ms,
warm switching 101.2 ms, and cache-eviction cycling 123.9 ms. Exact input,
rendered replay, focus and the three-parked-plus-one-active pane bounds passed.
This is not a new steady-state typing benchmark.

Across the six creation runs plus the tab run, all **1,940 browser and 2,306
server API records** were under 200 ms (maxima 108.0/100.79 ms). No browser,
request or request-failure errors were recorded. All 140 creations passed
unique live/saved identity, workspace isolation, rendered marker/native key,
selection/focus/socket, input-clock and pane-bound checks. Each fixture
completed cleanup and stopped its server. All 140 recorded producer PIDs were
independently checked absent; a final read-only listing with draining/pruning
disabled found none of the 146 exact owned creation/tab session names remaining.

Artifacts: `/tmp/lab-terminal-create-confirmed-{before,after,once,control,final,verified,tabs}-{browser,server}.json`
and associated logs; `/tmp/lab-terminal-create-confirmed-comparison.json`,
`/tmp/lab-terminal-create-confirmed-cleanup.json`; test logs
`/tmp/lab-terminal-create-confirmed-{tests,once-tests,guard-tests,membership-rejected-tests,final-tests,final-fallback-tests}.log`.
Intermediate source/test archives are
`/tmp/lab-terminal-create-confirmed-first.patch`,
`/tmp/lab-terminal-create-confirmed-before-close-guard.patch` and its `-test.py`,
and `/tmp/lab-terminal-create-confirmed-before-atomic-refresh.patch` and its
`-test.py`. The summary helper is `/tmp/lab-terminal-confirmed-summarize.py`.

Cold creation remains over budget, as do previously retained output-typing,
IME and navigation failures. Remaining UI/API coverage and physical/iTerm
parity are still unresolved. Main merge remains pending after the prior
automatic approval rejection. No merge, push or live server restart was attempted.


## Separate cold process startup from terminal rendering — 2026-09-23

The previous turn made production progress in `b3836b7`; this turn started
from that clean checkpoint. The remaining cold-creation miss was profiled,
a small renderer candidate was tested and fully removed, and diagnostic plus
fallback coverage was retained. Production lab-app.js is byte-for-byte equal
to `b3836b7`. No backend, vendor asset, startup workload or readiness budget
changed in this checkpoint.

### Rejected temporary-renderer shortcut

The six-creation CPU profile contained substantial aggregate font-width
measurement work, but the first creation window accounted for only about 6 ms
of the width cache's own sampled CPU. Its attachment preamble accounted for
about 55 ms inclusive, including roughly 22.5 ms in WebGL activation. Batch
profile totals therefore did not explain the entire cold sample.

The vendored core exposes an internal onWillOpen hook before choosing its
renderer. A candidate installed guarded WebGL activation there, then disposed
the listener in finally; the ordinary post-open path remained for cores without
that hook. This skipped initial DOM renderer construction while preserving
final fit before WebSocket connection. Real native checks covered DOM, WebGL,
forced context failure and an absent hook at three pane sizes, with Unicode,
focus and disposal. Initial test instrumentation failed because onWillOpen is
a getter and simple assignment did not replace it. After correcting the spy
with a property override, all four native cases passed; the other 148 focused
checks had already passed.

The native comparison did not establish an end-to-end improvement:

| Untraced 20-creation run | First / maximum | Median | p95 | Misses >200 ms |
| --- | ---: | ---: | ---: | ---: |
| Unchanged `b3836b7` frontend | 287.9 ms | 168.6 ms | 179.9 ms | 1 |
| Opening-renderer candidate | 319.4 ms | 165.2 ms | 183.5 ms | 1 |

The first POST was also slower in the candidate (55.21 vs 44.00 ms), so the
entire cold difference cannot be assigned to renderer ordering. POST medians
were similar (53.19 vs 52.35 ms). The small median difference, worse tail and
unchanged miss count did not justify retaining the private-hook optimization.
The source and candidate-specific assertions were removed together. The new
real-browser forced-GPU-failure case remains: DOM fallback must be fitted,
focused, preserve Unicode and latch the failed-GPU state across later panes.

Archive: `/tmp/lab-terminal-open-renderer-rejected.patch`; paired native runs
`/tmp/lab-terminal-open-renderer-{before,after}-{browser,server}.json` and logs;
`/tmp/lab-terminal-open-renderer-tests.log` (initial spy failures) and
`/tmp/lab-terminal-open-renderer-native-tests.log` (four corrected cases pass).

### Retained stage diagnostics

When LAB_PERF_TRACE is present, the existing terminal probe optionally records
write-parsed events, actual render events and changes to the already-computed
readiness predicates. It records timing/booleans, not buffer contents. A parsed
marker still cannot satisfy rendered readiness; cursor-row coverage, selected
workspace/session, focus, open socket, visible pane and exact text checks are
unchanged. Normal runs install no extra parse listener or diagnostic timeline.
Each pane's detail log is bounded to 1,000 entries with an explicit dropped
counter. The diagnostic runs below had zero dropped stage entries.

The creation fixture now reads the existing owned PID/cwd file's modification
time during cleanup and associates it with the exact session name. The shell
source is unchanged. This file is written before tty setup and initial marker
output; its mtime is a pre-output milestone, not an exact ready/write timestamp
or CPU measurement. The fixture continues validating PID/cwd, owned command,
exact session identity, purge and saved-state cleanup.

In the first stage-traced creation, the pane was focused at +154.3 ms and
selected/connected at +164.6 ms, but the exact marker was not parsed until
+237.8 ms. It rendered at +251.0 ms; the click/paint opportunity measurement
finished at 282.2 ms. Late focus was not the final missing condition in this run.

A second diagnostic correlated the process record: the first shell reached
that write at **+235.1 ms**, versus +47.1–56.0 ms for the next five. The first
exact marker parsed at +277.3 ms and rendered at +289.5 ms; creation completed
at 317.6 ms. Connection/focus were also later in that run, so this does not
attribute every remaining millisecond to the shell or identify whether its
startup interval was CPU work, scheduling or I/O waiting.

An **untraced** 20-creation recheck retained the same shell and workload. The
first process record appeared at **+219.7 ms**, before initial output, and the
first/full creation completed at **269.0 ms**. Later process records appeared
at +52.5–84.7 ms. Creation median/p95 was 167.4/190.2 ms, with 19/20 under 200 ms;
workspace opening was 138.1 ms and picker maximum 52.2 ms. No diagnostic timeline
was present. This demonstrates a cold cost before the fixture's first output;
it does not establish that production cold creation meets the target. Do not
replace the fixture shell, exclude the first sample, or shorten readiness to
turn that retained failure into a pass.

### Validation, failures and cleanup

**178 focused tests passed** with the restored production app, optional
stage diagnostics and real forced-GPU-failure coverage. The 27 fixture/probe
checks were rerun after adding process-file timestamps and passed; they verify
the actual saved mtime, unchanged ownership/foreign-session protection, parser
versus render readiness, default absence of diagnostics and explicit overflow.
JavaScript syntax checks and git diff --check passed.

All three diagnostic traces and CPU profiles cover the first measured action
through the last verified native-key render. Trace tails were 100.1–101.0 ms
past that final render; no trace data loss was reported. The two stage-enabled
runs had zero stage overflow. Traced creation results remain separate from
untraced comparisons: initial profile first/median 288.1/185.9 ms with two
misses; stage profile 282.2/188.2 ms with two misses; process profile
317.6/183.0 ms with two creation misses plus a **278.9 ms workspace miss**.
No failed sample was dropped.

Across the six runs, all **1,161 browser and 1,423 server API records** stayed
under 200 ms (maxima 108.8/99.77 ms), with no browser/request errors. All 78
creations passed rendered-marker/native-key, saved identity, workspace, focus,
clock and pane-bound checks. All fixtures completed cleanup and stopped their
servers. Every recorded producer PID was independently absent, and a final
read-only tmux listing with pruning disabled found none of the 78 exact names.

Artifacts: `/tmp/lab-terminal-{cold-current,cold-stages,cold-process,cold-process-untraced}-{browser,server}.json`
and associated logs; the three traced prefixes also have `-trace.json`, trace
metadata and `-cpu.json`. Summary and coverage evidence:
`/tmp/lab-terminal-cold-summary.json`, its `.py` helper,
`/tmp/lab-terminal-cold-cleanup.json`, `/tmp/lab-terminal-cold-stage-tests.log`
and `/tmp/lab-terminal-cold-process-record-tests.log`.

This is a diagnostic/correctness checkpoint, not a new production speed gain.
Cold creation, earlier output-typing/IME/navigation failures, unmeasured actions
and endpoints, and physical/iTerm parity remain unfinished. Main merge is still
pending after the earlier automatic approval rejection. No merge, push or live
server restart was attempted.

## Notebook draft restoration settles history before teardown — 2026-09-23

This checkpoint starts from `bac2beb`. A terminal launch candidate was measured
and removed. New notebook editing coverage exposed a repeatable workspace
restoration delay; the retained production change moves history normalization
and notebook position capture ahead of outgoing-view teardown.

### Retained production change

`goToWorkspace` already pushed history before clearing the old view, but
`selectRepo` still normalized the URL with `replaceState` after the body classes
were removed. The same normalization now happens before `_swapViewState` when
the destination is already in the catalog. Selection receives `historySettled`
only for that exact workspace object. Direct/initial selection and selection
after a deferred catalog lookup retain their original normalization path.
Replacement state remains null; URL fields, hash, entry count and popstate
behavior are preserved. `_swapViewState` also captures the final notebook
reading position before modifying the shell and clears its old listeners.
Terminal parking still uses the outgoing workspace.

Moving position capture alone did not materially improve repeated restoration.
The subsequent history change produced the measured gain below. No notebook
cells, outputs, source highlighting, persistence or freshness checks were
removed, and no new notebook cache or virtualization was introduced.

### Notebook workload and native results

`--notebook-view --notebook-typing --notebook-code-lines 500` measures native
letters, digits, spaces and Enter at the existing fixed 25 ms cadence. The
textarea is transparent in production, so each input and paint check verifies
its exact value/cursor/focus, connected/editable state, matching visible syntax
overlay text and exact localStorage draft. Keys continue dispatching without
waiting for renderer acknowledgments. Bad clocks and incomplete input fail.
The shared document observer's optional visible-state verifier defaults to a
no-op, preserving ordinary document measurements.

The fixture retains all 200 notebook cells, their complete outputs and controls,
5,000 mixed files and 2,500 Git changes per workspace. The first code cell has
an explicit 500-line Python source extension; the option defaults to zero so
the original viewing workload is unchanged. Every visit verifies all cells.
Two final workspace switches restore both latest drafts. Both notebook files
must remain byte-for-byte unchanged. This does not execute cells or measure
kernel start/interrupt, rich outputs or physical display latency. Native Tab
is not replaced with a synthetic indentation operation.

| Untraced 20-visit run | Repeated restoration median | Maximum | Click misses / 122 | Native keys / misses |
| --- | ---: | ---: | ---: | ---: |
| Original production code | 247.1 ms | 313.5 ms | 21 | 491 / 0 |
| Earlier position capture only | 250.1 ms | 264.9 ms | 19 | 491 / 0 |
| Position plus earlier history normalization | 162.7 ms | 167.6 ms | 0 | 491 / 0 |
| Final repeat | 163.1 ms | 170.3 ms | 0 | 491 / 0 |

The final two runs passed **244/244 native clicks and 982/982 native key checks
under 200 ms**. Their final-draft restoration maxima were 184.8 and 164.5 ms;
key maxima were 73.1 and 72.1 ms. These key results meet the general UI target;
they are not terminal/iTerm parity measurements. Original failures included
18/18 repeated restores, one workspace opening, one notebook opening and one
final restoration. None was excluded.

The initial four-visit expansion had three click misses (workspace 203.1 ms,
restoration maximum 259.8 ms), with 96 keys at maximum 52.2 ms. A verbose
diagnostic trace overflowed: its saved completion reported data loss, and its
late event ordering is unusable. It also perturbed the run heavily: six click
misses and all 96 keys above 200 ms, maximum 1,019.9 ms. A separate CPU-only
four-visit profile retained five click misses, restoration maximum 261.5 ms
and 96 keys at maximum 43.4 ms. Diagnostic results remain separate from the
untraced comparisons; no precise per-action attribution is claimed from the
incomplete trace. Code inspection identified the second history normalization
after shell teardown, and the unchanged native comparison established the gain.

### Other checks and cleanup

The 1,500-section document workflow passed 42 clicks (maximum 194.4 ms), 330
native keys (72.2 ms), 12 separate IME setups (189.7 ms), and Back/Forward
round trips (173.5/138.1 ms). Save/Cancel and history checked all four exact
files, both rendered views and unchanged history IDs/URLs. History durations
include controller acknowledgment and are separate from timestamped input.

The terminal regression passed all 48 actions under 200 ms: workspace opening
148.5 ms, first terminal activation maximum 134.7 ms, warm maximum 100.1 ms,
and cache-cycle maximum 132.1 ms. Exact text, selected session, focus, open
socket and the three-parked/four-total-pane bounds passed. Its six owned
sessions were removed and independently absent from an exact-name inventory
with pruning disabled.

**175 focused checks passed:** 173 passed in the initial run; two native Chrome
checks could not launch the browser inside the sandbox and passed when rerun
with browser-launch permission. The initial launch failures remain in the log.
Checks cover history ordering/fallback, URL/state preservation, Home terminals,
workspace deletion, notebook paths, document refresh/save, terminal creation,
sidebar/dashboard behavior, native clock validation and all new probe failure
guards. JavaScript syntax and `git diff --check` passed.

### Rejected direct-shell candidate

The installed tmux manual supports direct execution of multiple command
arguments. A terminal-only candidate passed `[shell, '-l']` directly, retaining
agent launch behavior and saved command metadata. It did not establish an
end-to-end cold-start improvement, so it was fully removed:

| Untraced 20-creation run | First / maximum | Median | p95 | Misses |
| --- | ---: | ---: | ---: | ---: |
| Original | 317.0 ms | 168.1 ms | 198.7 ms | 1 |
| Direct arguments | 281.1 ms | 167.8 ms | 183.1 ms | 1 |
| Direct arguments repeat | 267.3 ms | 168.3 ms | 181.3 ms | 1 |
| Restored original | 269.7 ms | 170.8 ms | 203.0 ms | 3 |

All 80 creations passed functional/identity/clock checks and owned cleanup.
Every recorded producer PID was absent, all 80 exact names were absent from
the read-only inventory, and all fixture servers stopped. The configured shell,
first sample and readiness predicates were unchanged. Production term.py is
unchanged from `bac2beb`.

Across all runs in this checkpoint, **4,065 browser and 4,538 server API records
were below 200 ms**, maxima 162.8/182.50 ms. All fixture servers stopped, and
there were no browser/request errors. This covers measured requests only.

Artifacts: `/tmp/lab-terminal-direct-shell-{before,after,repeat,control}-{browser,server}.json`
and logs, `/tmp/lab-terminal-direct-shell-candidate.patch`, and
`/tmp/lab-direct-shell-cleanup.json`; notebook
`/tmp/lab-notebook-typing-{initial,before,trace,cpu,after,history,final}-{browser,server}.json`
and logs (the trace/cpu prefixes also contain their diagnostics);
`/tmp/lab-notebook-history-{document,terminal}-{browser,server}.json` and logs;
`/tmp/lab-notebook-history-terminal-cleanup.json`;
`/tmp/lab-current-latency-summary.json` and its `.py`/`.log` helpers;
`/tmp/lab-notebook-{typing-probe,position,history}-tests.log`;
`/tmp/lab-notebook-history-{final,native}-tests.log`.

Cold terminal creation, previously retained terminal output-typing/IME/cold
navigation misses, unmeasured UI/API actions and physical/iTerm parity remain
unfinished. Main merge is still pending after the earlier automatic approval
rejection. No merge, push or live user-server restart was attempted.

## Bound and overlap repository-summary Git reads — 2026-09-23

This checkpoint starts from `c755f34`. Terminal output typing still misses its
50 ms target; private reader-thread controls did not establish a reliable fix.
The retained production change addresses a newly measured slow backend path:
`GET /api/code-search/repos`.

### Retained endpoint change and comparison

The endpoint ran two independent Git subprocesses per repository sequentially.
A 20-repository catalog therefore took roughly 500 ms even though each command
was short. `_repo_summary` retains the exact command sequence, timeouts, parsing,
branch fallback and response shape. A shared eight-worker executor overlaps
repositories, and ordered `map` preserves the existing case-insensitive catalog
order. The bound applies across simultaneous requests, including requests with
one repository. An empty catalog starts no workers; every nonempty request
still reads Git afresh.

The isolated fixture uses normal authentication, server lifespan and polling
watcher. Its 20 real repositories include empty and detached-HEAD cases,
Unicode/tab-containing subjects, and case-mixed names. Hidden and non-repository
entries are excluded. All stable metadata and ordering are checked for every
response; relative-age strings must remain present and nonempty. A final branch
change and commit check freshness. The committed probe additionally verifies all
20 rows after that mutation. Relative-age text is checked exactly in unit tests.
No first requests, slow samples or readiness steps were discarded.

| Fixed A/B/B/A run | First / maximum HTTP | Median HTTP | Regular request misses / 20 | Fresh metadata request |
| --- | ---: | ---: | ---: | ---: |
| Original | 547.4 ms | 498.5 ms | 20 | 489.8 ms |
| Shared eight-worker pool | 155.4 ms | 113.1 ms | 0 | 108.0 ms |
| Pool repeat | 160.9 ms | 116.6 ms | 0 | 113.3 ms |
| Restored original control | 560.8 ms | 495.3 ms | 20 | 468.9 ms |
| Restored candidate, committed probe | 169.5 ms | 109.5 ms | 0 | 111.5 ms |

The three 20-repository candidate runs passed **63/63 complete HTTP requests
under 200 ms**; maximum server ASGI duration was **168.15 ms**. A final
one-repository check also passed all **21/21 requests**, including its first
request: HTTP maximum 83.3 ms, median 34.6 ms, fresh-read 29.8 ms and server
maximum 82.19 ms. This verifies that single-repository requests can share the
worker bound without exceeding the budget. All 42 original/control requests
exceeded 200 ms. Every server stopped. The final committed probe separately
confirmed its temporary directory was removed. These are complete HTTP and
server measurements, not UI clicks: the current Code Search UI entry is a
placeholder. Larger catalogs and latency under concurrent real HTTP clients
remain unmeasured; the unit tests verify the cross-request concurrency bound.

The first disposable baseline completed its requests and stopped its server,
but its temporary diagnostic mistakenly called a nonexistent `ServerTimings.write`
method. That run produced no usable timing report. Its failure log is retained;
the writer was corrected to use `report()` before the recorded A/B/B/A sequence.

`scripts/perf/lab_code_search_latency.py --output /tmp/<unique-prefix>` reproduces
the final workload with the default 20 repositories and 20 regular requests.
Reports refuse overwrite, record response timings before validation, check all
rows after the final mutation, retain cold samples and exit nonzero on a 200 ms
miss. The fixture creates Lab metadata through the CLI and only changes its own
Git repositories.

Focused tests cover completion ordering, a shared eight-worker limit across three
requests, live metadata changes, all response fields, subject tabs, hidden and
non-repository entries, worktree pointers, empty/detached/error fallbacks and the
single-repository/worktree case. Initial endpoint/search validation: **11 passed**.
Final endpoint, search, terminal diagnostic/output-probe and WebSocket
reliability validation: **69 passed**. A preceding 69-check run also passed;
the final rerun follows the stricter bound that includes single-repository
requests. `git diff --check` passed. Terminal production code is unchanged.

Artifacts: `/tmp/lab-code-search-list-{before-report,after,repeat,control,final}-{http,server}.json`
and corresponding logs; `/tmp/lab-code-search-list-before.log` retains the failed
report writer; `/tmp/lab-code-search-list-benchmark.py` is the exact temporary
A/B/B/A driver; `/tmp/lab-code-search-checkpoint-summary.py` and `.json`;
`/tmp/lab-code-search-tests.log`, `/tmp/lab-code-search-final-tests.log` and
`/tmp/lab-code-search-final-bound-tests.log`; the final single-repository
check uses `/tmp/lab-code-search-single-final-{http,server}.json` and its log.

### Terminal output typing and rejected reader controls

Two unchanged native runs retained the 5,000 mixed files, 2,500 Git changes,
40 colored output lines every 50 ms, 25 ms input cadence, actual xterm rendering,
normal shared tmux generation, and 30 file updates/refreshes. Each delivered and
verified all 1,200 input bytes, source hashes, parse/render coverage and advancing
output without browser, transport or clock errors. Neither met the 50 ms goal:

| Native run | Output-only maximum / misses | Loaded-phase maximum / misses |
| --- | ---: | ---: |
| Untraced current checkpoint | 34.7 ms / 0 | 94.8 ms / 17 |
| Reduced trace plus CPU/source diagnostics | 70.6 ms / 25 | 46.4 ms / 0 |

The untraced run's single 53 ms long task occurred **before typing began** and
does not explain its misses. The reduced trace reports no data loss. Its actual
renderer events span the first dispatched key through the final actual render;
the CPU profile's timestamp span also covers that interval. This verifies time
coverage, not precise attribution of every delay. No production sidebar/Git
change was made from aggregate CPU-profile totals. Source-write waiting remains
visible, and the slow phase changes between runs. Instrumented and untraced
latencies are not pooled into one result.

A new private-PTY component diagnostic compared selector and continuously
reading thread modes in fixed A/B/B/A order, with 600 inputs per run and the
same producer/geometry. The first comparison was confounded: actual input
lateness reached 10.12 ms with foreground sleep versus 2.17 ms with the selector.
Its apparent large improvement is not accepted as evidence for a transport fix.

A second A/B/B/A capped both waits at 1 ms. Actual lateness stayed below 0.61 ms,
but write stalls remained. A third comparison used nonblocking reads in a
separate thread, retaining the input fd's nonblocking behavior:

| Matched-cadence component mode, in run order | Producer writes over 10 ms | Producer-write p95 | Maximum |
| --- | ---: | ---: | ---: |
| Selector, blocking-reader comparison | 29 | 12.13 ms | 12.80 ms |
| Blocking reader thread | 19 | 11.60 ms | 12.70 ms |
| Blocking reader thread repeat | 8 | 0.29 ms | 12.52 ms |
| Selector control | 20 | 11.72 ms | 12.84 ms |
| Selector, nonblocking-reader comparison | 35 | 12.04 ms | 12.68 ms |
| Nonblocking reader thread | 12 | 0.31 ms | 13.05 ms |
| Nonblocking reader thread repeat | 25 | 12.02 ms | 15.91 ms |
| Selector control | 21 | 11.72 ms | 12.65 ms |

The nonblocking thread did not establish a consistent improvement; no production
reader implementation was changed. These private controls have no browser,
WebSocket, xterm negotiation/rendering or live Git workload. Frame/byte-count
changes alone do not establish latency gains.

An initial nonblocking comparison stopped after its first 600-input selector run
because the immediate cleanup check still saw the private server exiting.
A subsequent PID check found all three owned processes gone; only then was the
same recorded socket inode unlinked. The repeat waited boundedly for both owned
producer and server exit. The original failure remains in its manifest/log.
An independent final audit found all **13 private runs' producer, attachment and
server PIDs absent**, all private sockets absent, and both exact native fixture
session names absent from a read-only inventory with pruning disabled.

Artifacts: `/tmp/lab-output-checkpoint-{current,profile}-{browser,server,summary}.json`
and logs; profile `-trace.json`, trace metadata and `-cpu.json`;
`/tmp/lab-output-current-coverage.py` and `.json`;
`/tmp/lab-pty-boundary-{reader-thread-abba,reader-thread-cadence-abba,reader-nonblocking-abba,reader-nonblocking-wait-abba}.json`
and their per-run `root` directories; the corresponding `/tmp/lab-pty-reader-*.py`
drivers and logs; `/tmp/lab-pty-reader-nonblocking-failed-cleanup.json`;
`/tmp/lab-reader-and-output-cleanup.py` and `.json`.

Cold terminal creation, retained terminal output/IME/navigation misses,
unmeasured UI/API actions and physical/iTerm parity remain unfinished. The
scope question about completion versus immediate acknowledgment for inherently
long notebook/Git operations remains unanswered; those API semantics are
unchanged. Main merge remains pending after the earlier automatic approval
rejection. No merge, push or live user-server restart was attempted.

## Preserve Apple's Git context while avoiding repeated launcher work — 2026-09-23

This checkpoint starts from `bc6d8f5`. The previous turn made concrete progress
by committing the bounded repository-summary reads. Its single-client results
did not prove concurrent-request latency. The current worktree was clean at
that commit before extending the workload.

### Concurrent requests expose repeated process-launch cost

`lab_code_search_latency.py --clients 2` now runs independent authenticated HTTP
clients, released together for each of 20 rounds, against the unchanged
20-repository fixture. Every response still verifies ordered stable metadata,
empty/detached repositories, Unicode/tab-containing subjects and exclusions.
A final branch/commit mutation checks all returned rows. The first pair is
retained. Default `--clients 1` keeps the original direct call path; no worker
thread is started for its request dispatch. The probe supports one through
eight clients and retains HTTP failures before validation.

Epoch timestamps are retained, and the final probe also records monotonic
start times, start skew and actual overlap. Non-overlapping concurrent requests
fail. In the final candidate, the maximum start skew was **0.365 ms**, and every
pair overlapped for at least **126.05 ms**. This is HTTP completion timing, not
browser dispatch or paint.

The initial eight-worker baseline missed 200 ms on **21/40 requests**, maximum
290.3 ms. Simply raising the limit to sixteen did not solve the problem:
**27/40 misses**, median 203.1 ms, maximum 243.5 ms. That limit was removed.

A private-process A/B/B/A control used the same owned repository, command,
exact Git output and 100 samples per run. Removing `communicate`'s timeout did
not materially change the roughly 10.6 ms command median; final process waits
were about **0.005–0.007 ms**, while spawning took roughly 1.1–1.2 ms. No timeout
was removed in production.

PATH selects `/usr/bin/git` on this Mac, which delegates through Apple's
command-line tool selection. Apple documents these launchers and `xcrun` in
[its command-line tools FAQ](https://developer.apple.com/library/archive/technotes/tn2339/_index.html).
A separate A/B/B/A control compared that launcher with the executable returned
by `xcrun --find git`. All 400 outputs matched. Command medians were **10.56,
4.94, 4.95 and 10.68 ms**, respectively. That component comparison suggested
an endpoint optimization; it did not itself prove HTTP latency.

### Retained production behavior

For a nonempty repository catalog on Darwin, and only when PATH selects the
exact `/usr/bin/git` launcher, `_git_invocation` resolves the selected Git once
for that request. It also asks `xcrun /usr/bin/env -0` for the launcher-prepared
environment. Directly using the Git binary without this changed **CPATH,
LIBRARY_PATH, MANPATH and SDKROOT** in a controlled comparison. Supplying the
prepared environment made the full child environment equal in default,
custom-include/library/manual-path, and explicit developer-directory/SDK cases.
The last case used the selected Command Line Tools directory and `SDKROOT=macosx`.

The executable and environment are request-local, with no persistent cache.
Environment values are neither logged nor returned. Each request therefore
rechecks tool selection. Other platforms, custom PATH Git installations and
wrappers retain their original path. Empty catalogs skip discovery. Failed,
malformed, unavailable or timed-out discovery falls back to ordinary Git.
If the selected executable disappears, loses permission, or cannot execute
during a toolchain update, the same read command falls back to the launcher.
Existing Git arguments, per-command timeouts, response fields, parsing and
legacy failure behavior are retained. Both commands for every repository share
the captured invocation; catalog ordering and fresh metadata remain intact.

The shared Git worker limit remains **eight**. A resolved-Git twelve-worker
trial passed but had essentially the same median as the eight-worker repeat
(149.1 versus 149.5 ms), so there was insufficient evidence to retain the larger
limit. No user PATH, Git installation, developer-tool selection or environment
setting was changed.

### Complete HTTP results

| Two-client run, in measured order | Median | Maximum | Misses / 40 | Final fresh read |
| --- | ---: | ---: | ---: | ---: |
| Original eight-worker code | 223.7 ms | 290.3 ms | 21 | 124.0 ms |
| Rejected sixteen-worker limit | 203.1 ms | 243.5 ms | 27 | 110.1 ms |
| Request-local Git context, eight workers | 151.7 ms | 208.8 ms | 1 | 82.0 ms |
| Eight-worker repeat | 149.5 ms | 195.9 ms | 0 | 108.8 ms |
| Rejected twelve-worker limit with context | 149.1 ms | 188.9 ms | 0 | 85.2 ms |
| Restored original eight-worker control | 205.7 ms | 262.9 ms | 20 | 114.3 ms |
| Restored final eight-worker candidate | 150.2 ms | 187.0 ms | 0 | 83.2 ms |

The two later retained eight-worker runs passed **80/80 concurrent requests**
and both freshness checks under 200 ms. Their maximum server ASGI time was
194.30 ms; the final run's server maximum was 183.53 ms. The earlier **208.8 ms
HTTP / 207.89 ms server miss remains recorded**. The before/control and candidate
runs are not presented as a guarantee against all future tail latency.

A final single-repository check passed **21/21 requests**: first/maximum 81.5 ms,
median 34.2 ms and fresh-read 32.1 ms; maximum server time 80.15 ms. This catches
regression from the extra request-local discovery on small catalogs.

### Statistics coverage, correctness and cleanup

The unchanged statistics endpoint also passed **21/21 complete HTTP requests**
with one real owned repository containing **10,001 commits, 5,000 tracked files
and 33 authors**. HTTP first/maximum was 141.7 ms, median 101.5 ms; maximum server
time was 140.42 ms. A subsequent new commit, tracked file and remote URL change
returned all four exact updated fields in 98.3 ms. History was generated with
Git fast-import in the disposable repository; no user repository was changed.
Statistics still uses its original Git commands and invocation path. This
extends coverage, not a statistics-endpoint optimization or proof for arbitrary
history sizes.

**96 regression checks passed**, covering repository/search behavior, native
launcher-environment equality, terminal diagnostics/output probes and WebSocket
reliability. After adding three fallback cases, **41 focused repository/search
checks passed**. These counts overlap. Checks include custom/absent PATH Git,
non-Darwin behavior, executable validation, malformed and binary-safe environment
parsing, discovery failures/timeouts, selected-tool execution failures, original
Git errors, request-local selection, fresh metadata, shared bounds and ordering.
No production terminal code was changed. Syntax checks and `git diff --check`
passed. All nine HTTP fixtures stopped their servers and removed their owned
temporary directories. Component subprocess controls completed/reaped every
child; no user tmux session or live Lab server was reconfigured or stopped.

Artifacts: `/tmp/lab-code-search-{concurrent-before,concurrent-sixteen,concurrent-resolved,concurrent-resolved-repeat,concurrent-resolved-twelve,concurrent-control,concurrent-final,resolved-single,stats-current}-{http,server}.json`
and logs; `/tmp/lab-code-search-resolved-summary.py` and `.json`;
`/tmp/lab-code-search-stats-benchmark.py`;
`/tmp/lab-git-{wait,wrapper}-control.py`, `.json` and `.log`;
`/tmp/lab-git-env-equivalence.json` (key names and equality only, no environment
values); `/tmp/lab-code-search-invocation-tests.log`,
`/tmp/lab-code-search-resolved-final-tests.log` and
`/tmp/lab-code-search-resolved-fallback-tests.log`; the final focused rerun
is `/tmp/lab-code-search-resolved-fallback-final-tests.log` and keeps any
environment-difference failure output limited to variable names.

The overall goal remains open: earlier cold terminal creation, output typing,
IME/navigation misses, unmeasured UI/API paths, physical/iTerm parity and the
scope of inherently long-running operation completion still need work. The
main merge remains pending after the earlier automatic approval rejection.
No merge, push or live user-server restart was attempted.

## Terminal creation: startup control and rejected combined tmux client

This checkpoint adds native API regression coverage and records a rejected
optimization. **Production terminal code remains identical to `361fee7`.**
The combined spawn/configuration client reduced request time slightly but
changed user-hook failure behavior, so it was removed.

### Unchanged native browser workload

Four serial runs each created 20 terminals in the normal disposable navigation
fixture, with 5,000 mixed files per workspace, 2,500 Git changes, the configured
echo shell, native clicks and keys, actual xterm render checks, saved identity,
workspace isolation and the existing parked-pane bound. No first launch or
budget miss was omitted. These are before/candidate/candidate/control runs:

| Implementation | Creation median | First creation | Creation p95 | POST median | POST max |
| --- | ---: | ---: | ---: | ---: | ---: |
| Original | 167.0 ms | 848.3 ms | 204.9 ms | 47.9 ms | 70.6 ms |
| Rejected combined client | 165.3 ms | 303.0 ms | 180.4 ms | 45.4 ms | 55.3 ms |
| Rejected candidate repeat | 163.6 ms | 300.8 ms | 173.6 ms | 42.3 ms | 59.8 ms |
| Restored original control | 166.4 ms | 285.3 ms | 190.6 ms | 54.7 ms | 60.8 ms |

Every first creation exceeded 200 ms. The original run also retained a
204.9 ms warm creation. Workspace opening missed at 218.3 ms initially and
204.6 ms in the restored control. All four runs had zero browser errors,
failed requests or HTTP errors; passing request budgets do not erase the UI
misses. Candidate cold timings are not claimed as an improvement: the restored
control was faster than both candidates on that measure.

### Shell startup component

On the initial 848.3 ms creation, the POST finished 44.5 ms after the click and
xterm was constructed at 95.8 ms. The unchanged shell's existing PID/cwd file
was written at 800.1 ms, before tty setup and first output. This places most of
that delay before the source's first record, rather than in xterm rendering.
It does not identify the underlying system mechanism or pure interpreter CPU.
The corresponding source-record milestones in the next three runs were
254.6, 250.6 and 237.1 ms.

A separate direct-PTY component control launched four fresh copies of the
**same echo-shell body**, ten times each. Each received the same `-l` argument;
the probe verified PID/cwd, exact readiness output and a UTF-8 echo. First
ready times were **170.7, 142.0, 143.4 and 144.0 ms**; the remaining nine-launch
medians were **17.9, 17.7, 17.9 and 17.6 ms**. Popen returned in 1.2–1.8 ms on
the four first launches, and the PID-file timestamp was within 0.5 ms of ready.
This demonstrates a first-launch delay without tmux, WebSocket or browser;
it does not explain the full original 800 ms source milestone. This component
does not replace the normal tmux creation benchmark or measure iTerm/physical
keyboard/display latency. The original browser fixture and shell were not
prewarmed or changed. An initial component attempt failed its cwd assertion
because `/tmp` resolves to `/private/tmp`; its child was reaped before the
canonical-path retry. All 40 completed-control children were reaped and the
temporary fixture removed.

### Why batching was rejected

The candidate sent new-session and the four existing wheel commands in one
tmux client invocation. It used the documented
[`new-session -P -F` output](https://man.openbsd.org/tmux#new-session) as a
creation marker so a later wheel error could remain best-effort. Ordinary
creation, duplicate rejection, immediate exit and later setting failure passed
117 initial checks. An added native `after-new-session` hook-error case then
found that **new-session can create the pane, print the marker and still fail
its hook**. The candidate incorrectly returned success. Moving the marker to
a separate following display-message command did not solve the problem.

The new native API regression reproduced the defect as HTTP 200 from the
candidate versus HTTP 500 from the restored implementation. On the restored
path it also verifies that wheel settings and success metadata remain
untouched after the failed hook. A second native API test checks shell argv
with spaces and the login flag, cwd, named socket, wheel settings, another
session's inherited options, durable saved identity and repeat-create adoption.
Both run on private owned tmux servers, independent of user sessions.

After restoration, **110 existing terminal checks and both new native API
checks passed**. The first restored suite had 111 passes and one test assertion
failure from expecting unnecessary quotes around `-l`; comparing parsed argv
fixed the assertion, and both native tests then passed. The hook regression
already passed in that restored suite. Native teardown verified all private
server/pane processes exited. The four browser fixtures stopped their servers,
reported cleanup complete, and a separate read-only audit found all **80 exact
session names and 80 recorded PIDs absent**.

Artifacts: `/tmp/lab-terminal-current-checkpoint-{browser,server}.json`,
`/tmp/lab-terminal-spawn-batch-{after,repeat,control}-{browser,server}.json`,
their logs and `/tmp/lab-terminal-spawn-batch-summary.json`;
`/tmp/lab-terminal-startup-component.py`, `.json`, `.log` and `-retry.log`;
`/tmp/lab-terminal-spawn-batch-candidate.patch`, `-rejected.patch` and
`-rejected-tests.py`; `/tmp/lab-term-spawn-batch-{tests-retry,hooks-tests,hooks-retry-tests}.log`;
`/tmp/lab-term-create-native-{candidate,restored,final}-tests.log`.

The latency goal remains open. No production optimization is claimed by this
checkpoint. Cold creation, occasional workspace/typing misses, broader path
coverage and physical/iTerm parity remain unresolved. The main merge remains
pending after the earlier automatic approval rejection; no merge, push or live
user-server restart was attempted.

## Reduce sidebar scan work while notebooks are pending

The previous empty-registry optimization left the busy case unchanged: even
one active notebook made every sidebar notebook resolve all its path ancestors.
This checkpoint removes that work for unrelated ordinary filenames on POSIX,
while preserving the existing full lookup for possible matches and aliases.

### Retained behavior and new workload

Under the same pending lock, a small nonempty registry first compares the
requested final filename with the resolved pending keys. If none matches,
lstat can prove an existing entry is a regular file, allowing a false result
without resolving its ancestors. Matching names, symlinks, missing or
inaccessible entries, unusual final path components and non-POSIX systems keep
the original resolution. A limit of 16 active paths bounds the extra name
search; larger registries keep the old path. No pending state, file identity or
negative result is cached. Empty-state behavior and run counting are unchanged.

Both scan and browser fixtures now accept `--pending-notebooks`. The scan
fixture marks that many owned files; navigation marks that many per workspace.
These are **pending-tracker fixtures, not notebook execution benchmarks**. They
use the normal marker/operation-lease functions and clear them on exit. The
browser checks exact cached pending paths and rendered running indicators
after every workspace navigation. The scan comparison checks complete response
equality and exact pending paths, then clears the markers and verifies both
implementations immediately remove pending fields without file edits. Its
report retains every individual duration and the two final fresh-read timings.

### Alternating full-ASGI component checks

Each row below contains 20 alternating samples per implementation against
`ef11b4e`, using 5,000 notebook files. All first samples are retained. This is
FastAPI TestClient with validation/serialization and thread dispatch; socket
transport and normal background services are measured separately below.

| Active paths | Original median / maximum | Candidate median / maximum |
| --- | ---: | ---: |
| 0 | 19.85 / 24.83 ms | 19.76 / 21.94 ms |
| 1 | 110.62 / 113.66 ms | 37.45 / 42.27 ms |
| 16 | 110.34 / 119.70 ms | 43.90 / 47.13 ms |
| 17, original-resolution fallback | 110.81 / 125.31 ms | 110.85 / 119.53 ms |

All 160 timed responses matched, every pending identity was verified, and all
markers/leases cleared. Six final fresh reads were below 21.53 ms. A further
one-pending comparison after adding the explicit POSIX guard retained equality:
original median/max **123.46/145.29 ms**, final candidate **43.22/48.67 ms**;
cleared reads were 23.97/23.63 ms. The guard leaves this POSIX fast path in place
and retains the original resolver on other platforms. The non-POSIX branch is
covered with a resolver double, not a native Windows performance claim.

### Native browser comparison

Five fresh-browser runs used normal server lifespan/polling, 5,000 notebook
files per workspace, 2,500 Git changes, one owned pending marker in each
workspace, and 20 workspace plus 20 document clicks. Only the production
pending helper was restored for the control; the workload and readiness
predicate stayed the same.

| Run | Workspace first / maximum | Workspace p95 | File-list median / maximum | UI misses |
| --- | ---: | ---: | ---: | ---: |
| Original before | 232.6 / 248.0 ms | 232.6 ms | 106.33 / 205.44 ms | 2 / 40 |
| Candidate | 164.0 / 164.0 ms | 146.4 ms | 40.31 / 72.30 ms | 0 / 40 |
| Candidate repeat | 231.4 / 231.4 ms | 159.9 ms | 44.78 / 144.80 ms | 1 / 40 |
| Restored original control | 319.6 / 319.6 ms | 278.9 ms | 111.78 / 270.01 ms | 2 / 40 |
| Restored candidate | 183.0 / 183.0 ms | 166.4 ms | 43.83 / 123.35 ms | 0 / 40 |

The candidate passed **119/120 actions**; its 231.4 ms cold opening remains a
failure. Warm workspace medians remained around 99–100 ms for both versions,
so this is chiefly a scan/cold-navigation improvement, not a claim that every
warm click became faster. Document maxima across all runs were 61.3–68.0 ms.
The candidate's 1,002 browser API records and 1,089 server API records were all
under 200 ms (maxima 146.0/144.80 ms). The controls retained four server API
misses, including the 205.44 and 270.01 ms file-list maxima. There were no HTTP,
network or browser errors. All 100 workspace switches verified their pending
metadata and running dots. All five servers stopped, markers and leases were
cleared, and their fixture directories were independently verified removed.

Before targeting the busy case, the ordinary mixed-file navigation baseline
passed 40/40 actions, workspace/document maxima 150.6/70.1 ms. A separate
instrumented browser/CPU/file-scan/watcher run retained nine workspace misses,
maximum 255.4 ms; its slowest file handler was 61.50 ms and it did not reproduce
the earlier 165 ms mtime request. No polling or watcher policy was changed,
and those diagnostic misses are not relabeled as passing performance evidence.

### Validation and limits

**117 focused checks passed**, including notebook execution-route behavior,
workspace scans, worktree metadata and timing instrumentation. Added cases
exercise same-name files in different directories, symlinked ancestors and
retargeting, regular-to-symlink replacement, missing targets, lstat failure,
parent-directory resolution, queued counts, small/large registries and the
non-POSIX fallback. Existing tests also verify pending transitions without file
edits. Python/JavaScript syntax checks and `git diff --check` passed. The older
broad suite's known baseline failures remain separate.

Artifacts: `/tmp/lab-busy-notebooks-{before,after,repeat,control,final}-{browser,server}.json`
and logs; `/tmp/lab-busy-notebooks-summary.json`;
`/tmp/lab-busy-notebooks-{before,after}-asgi.json`;
`/tmp/lab-busy-notebooks-final-{0,1,16,17}-asgi.json` and logs;
`/tmp/lab-busy-notebooks-guarded-final-asgi.json`;
`/tmp/lab-busy-notebooks-{tests,final-tests}.log`;
`/tmp/lab-workspace-current-{before,profile}-{browser,server}.json`, logs,
and profile `-trace.json`, trace metadata and `-cpu.json`.

The overall goal remains open: the retained cold miss, terminal creation and
output-typing tails, broader UI/API coverage and physical/iTerm parity still
need work. No terminal behavior, notebook execution semantics or API completion
semantics changed. Main merge remains pending after the earlier automatic
approval rejection; no merge, push or live user-server restart was attempted.

## Parse capped code-search results without splitting unused output

The 5,000-file code-search workload returns 100 results from 100,000 matching
lines (27,455,000 captured characters). The old parser split the entire output
before applying the response limit. The retained change lazily visits nonempty
lines and stops parsing at the existing limit. It preserves all of Python's
[`str.splitlines()` boundaries](https://docs.python.org/3/library/stdtypes.html#str.splitlines),
result order, malformed/binary-line handling, path normalization, integer
conversion, Unicode snippets, the 300-character snippet cap and exact-limit
truncation. Both ripgrep and Git fallback parsing use the same path.

Command invocation, output capture, full decoding, completion, timeouts and
ripgrep's thread policy are unchanged. No search result or negative result is
cached. The Code Search UI entry remains a placeholder; these measurements
cover the implemented backend route, not a browser search interaction.

### Full HTTP comparison

The reusable `scripts/perf/lab_code_search_latency.py` now accepts
`--repos 1 --search-files 5000`. It creates a disposable CLI-managed vault and
real Git repository, runs the normal authenticated server with polling, and
retains every first/subsequent response. Each response must contain exactly
100 unique valid file/line pairs and the exact expected snippets. A newly
committed Unicode result must appear immediately in the final fresh query.
The existing catalog workload remains the default; neither its verification
nor its concurrent-client barriers were relaxed.

Each run below contains 20 timed HTTP requests plus the fresh query. Original
controls use `873e785`; only `code_search.py` was restored for the later control.
The candidate repeat uses the restored final production source.

| Run | First / maximum | Median | Requests at or above 200 ms | Fresh query |
| --- | ---: | ---: | ---: | ---: |
| Original before | 284.30 / 284.30 ms | 233.81 ms | 19 / 20 | 120.91 ms |
| Initial lazy parser | 222.42 / 222.59 ms | 218.24 ms | 18 / 20 | 124.78 ms |
| Retained parser | 265.51 / 265.51 ms | 221.10 ms | 19 / 20 | 122.10 ms |
| Restored original control | 275.49 / 275.49 ms | 234.48 ms | 20 / 20 | 119.72 ms |
| Retained parser repeat | 255.52 / 255.52 ms | 218.11 ms | 17 / 20 | 119.05 ms |

All 100 timed responses and five fresh queries passed content verification;
all servers stopped and fixture roots were removed. The median improvement is
about 13–16 ms. **The large-search endpoint still misses 200 ms.** First requests
and misses remain in the reports; command execution/capture dominates the
remaining time.

A separate parsing-only diagnostic alternated original/candidate order for
40 pairs using identical complete captured output, with exact response equality.
Original median/max parsing was **14.887/15.864 ms**; candidate **0.138/0.174 ms**.
Separate, untimed tracemalloc checks measured peak allocations of
**32,310,831 versus 42,207 bytes** beyond the existing captured string. These
component figures exclude subprocess execution, decoding, transport and UI.

### Rejected output-capture change

Redirecting stdout to a private temporary file reduced parent-side pipe work.
Two full candidate runs had medians 146.35 and 150.78 ms, but retained cold
misses of 254.85 and 236.56 ms. This implementation was **removed** after a native
completion regression: a wrapper forks a descendant, the descendant closes
stderr, and the wrapper exits before the descendant writes stdout. File-backed
capture returned only the first row; the original pipe waits for stdout EOF
and returns both rows. Waiting for the parent and stderr is insufficient.
The failing case is now a passing regression against the retained capture path.

Earlier component diagnostics recorded default-pipe subprocess median/parent
thread CPU of 215.34/58.81 ms versus file-backed 137.34/15.96 ms. A one-thread
ripgrep diagnostic had HTTP median 173.26 ms and a 217.28 ms maximum; this was
not retained, since it changes tool scheduling and has no established benefit
for sparse-search workloads. Neither diagnostic is a claim that the target
has been achieved. The full captured output and every latency failure remain
available in their raw artifacts.

### Verification and remaining scope

**159 focused checks passed**, covering both search backends, all 11 line-boundary
forms, result limits, invalid lines, ignored nonzero tool returns, strict decoding
past the result cap, original command arguments, delayed descendant output and
native timeout child cleanup. Existing repository/Git-invocation/search-route
checks passed in the same run. Python compilation, CLI argument checks and
`git diff --check` passed. The older broad-suite baseline failures remain separate.

The benchmark's unchanged default catalog passed 40 concurrent HTTP responses
(two clients, 20 rounds), maximum **197.71 ms**, plus the fresh metadata query
at 86.30 ms. A four-file smoke check verified the uncapped 80-result branch and
new Unicode result, maximum 50.60 ms and fresh query 13.26 ms. Both fixtures were
removed and servers stopped. This small check validates fixture branching; it
does not replace the large workload.

Artifacts: `/tmp/lab-code-search-{matches-before,matches-lazy,lazy-retained,lazy-control,lazy-repeat}-{http,server}.json`
and logs; `/tmp/lab-code-search-matches-summary.json`;
`/tmp/lab-code-search-parser-comparison.{py,json}`;
`/tmp/lab-code-search-{process-default,process-one,process-file,matches-capture,matches-repeat}-{http,server}.json`;
`/tmp/lab-code-search-file-capture-rejected.patch` and `-tests.py`;
`/tmp/lab-code-search-capture-descendant-tests.log`;
`/tmp/lab-code-search-lazy-final-tests.log`;
`/tmp/lab-code-search-{catalog-regression,small-fixture-check}-{http,server}.json`.

The overall goal remains open, including large code searches, retained cold
navigation/terminal-creation misses, terminal output typing tails, broader
UI/API coverage and physical/iTerm parity. Main merge remains pending after
the earlier automatic approval rejection; no merge, push or live user-server
restart was attempted.

## Bound workers for eligible literal searches on larger Macs

The retained change requests **two ripgrep workers** for queries containing no
regex metacharacters, only on macOS machines reporting more than four CPUs and
without a nonempty `RIPGREP_CONFIG_PATH`. Queries remain unchanged; no fixed-string
flag is added. The classifier conservatively includes the contextual characters
`#`, `&`, `-` and `~` as well as the ordinary regex operators. See the regex
library's [metacharacter contract](https://docs.rs/regex-syntax/latest/regex_syntax/fn.is_meta_character.html).
Regex queries, configured tools, small/unknown CPU counts, other platforms and
the Git fallback retain their original worker policy. Environment and CPU
information are read afresh per request. There is no result cache or extra
filesystem scan.

The configuration guard matters because explicit command-line options can
override config-file flags; the [ripgrep configuration guide](https://github.com/BurntSushi/ripgrep/blob/15.2.0/GUIDE.md#configuration-file)
describes this precedence. Native tests preserve configured sorting and case
folding. Output remains fully captured through the original pipes and strictly
decoded before parsing, with unchanged process completion and timeout behavior.
The delayed-descendant and invalid-late-byte regressions continue to pass.

### Why two workers, and why only eligible literal queries

A new reusable `scripts/perf/lab_code_search_workers.py` compares complete native
subprocess runs. Defaults create 5,000 small files plus 64 separate 4 MiB files,
rotate the order of five worker variants across five rounds, retain all first
samples, and compare hashes of the entire sorted output, status and stderr.
The corpus and all command arguments other than worker count remain identical.
The final reusable run verified all **100 samples** and removed its fixture.
These are subprocess measurements, not HTTP or UI latency.

| Workload | Default median | 1 worker | 2 workers | 4 workers | 8 workers |
| --- | ---: | ---: | ---: | ---: | ---: |
| 100,000 matches in 5,000 small files | 216.54 ms | 162.47 ms | 122.20 ms | 93.90 ms | 184.88 ms |
| One match among 5,000 small files | 121.64 ms | 62.10 ms | 42.15 ms | 36.10 ms | 104.65 ms |
| One match across 256 MiB of larger files | 17.07 ms | 33.79 ms | 23.72 ms | 18.34 ms | 16.23 ms |
| Regex across the same 256 MiB | 62.10 ms | 337.83 ms | 174.61 ms | 104.18 ms | 68.96 ms |

An earlier independent 100-sample diagnostic showed the same tradeoff. A universal
small pool would substantially regress the CPU-heavy regex workload. Even for
literal queries, the sparse large-file case is slower with two workers; its
measured roughly 7 ms cost is retained here rather than hidden. Four workers
looked best for a single small-file search, but the HTTP concurrency check below
favored two. No claim is made that this synthetic corpus covers every repository.

Larger stdout reads were also rejected without a production change. A
request-local diagnostic copy of the standard collector used 32 KiB versus
1 MiB reads while keeping full pipe completion. HTTP medians were 219.26 versus
222.26 ms; parent-thread CPU medians were 58.43 versus 62.75 ms. Fewer reads did
not establish a latency improvement. The earlier file-backed collector remains
rejected for losing delayed descendant output.

### Complete HTTP comparisons

Every run uses the same 5,000-file/100,000-match workload, authenticated server,
normal polling, limit of 100, and exact row/snippet/uniqueness checks. Each run
includes a fresh committed Unicode result. Single-client runs contain 20 timed
requests; two-client runs contain 20 overlapping pairs. Original controls use
`8487679`'s worker policy. Diagnostic overrides below alter only the requested
worker count inside the owned fixture. No waits, budgets, first samples or
response predicates were changed.

| Single-client run | First / maximum | Median | Misses >=200 ms | Fresh query |
| --- | ---: | ---: | ---: | ---: |
| Original control | 256.99 / 256.99 ms | 219.55 ms | 18 / 20 | 108.17 ms |
| Four-worker candidate | 171.92 / 171.92 ms | 103.20 ms | 0 / 20 | 38.55 ms |
| Four-worker repeat | 138.53 / 138.53 ms | 97.79 ms | 0 / 20 | 38.76 ms |
| Two-worker diagnostic | 198.50 / 198.50 ms | 137.53 ms | 0 / 20 | 54.74 ms |
| Final two-worker production source | 199.93 / 199.93 ms | 142.20 ms | 0 / 20 | 50.98 ms |

| Two-client run | Maximum | Median | Misses >=200 ms | Fresh query |
| --- | ---: | ---: | ---: | ---: |
| Original policy | 428.56 ms | 382.46 ms | 40 / 40 | 130.10 ms |
| Four workers | 364.06 ms | 322.96 ms | 40 / 40 | 40.06 ms |
| One worker | 327.57 ms | 269.45 ms | 40 / 40 | 75.62 ms |
| Two-worker diagnostic | 266.08 ms | 207.56 ms | 38 / 40 | 52.55 ms |
| Final two-worker production source | 272.64 ms | 201.75 ms | 26 / 40 | 53.91 ms |

The final policy improves both single and overlapping-client latency. Its
single-client cold sample has only **0.074 ms** of margin: the passing run is
not evidence of a reliable cold-start guarantee. **Concurrent searches still
fail the budget**. The four-worker candidate is not the retained implementation,
and its faster single-client numbers must not be presented as the final result.
All 300 timed responses in these completed comparisons verified their content;
all ten fresh queries passed, servers stopped, and fixture roots were removed.

Two earlier diagnostic attempts failed with HTTP 500 before producing latency
comparisons: a diagnostic variable named `workers` was later reused for the
client executor and leaked that object into the command argument list. The
fixture override now captures its own named selection. Both failure reports
are retained, both servers stopped, and a final filesystem inventory found no
remaining owned HTTP fixture roots. These were diagnostic harness failures,
not failures of the production helper; they are not included as passing samples.

### Verification and remaining work

**202 focused checks passed** with the final two-worker source. Coverage includes
all regex metacharacters, Unicode/plain queries, invalid regexes, config changes,
other platforms, small/unknown CPU counts, exact remaining command/capture
options, both search backends, and the existing repository/Git/search routes.
Native ripgrep checks compare complete uncapped results across worker policies,
verify ignored and hidden files, validate line/snippet identity, and retain exact
configured sorted/case-folded results across the cap. The capture regressions
retain timeout child cleanup, strict late decoding and descendant stdout EOF.
The new benchmark's default 100 samples passed full-output equality checks;
Python compilation, CLI rejection checks and `git diff --check` also passed.
The older broad-suite baseline failures remain separate.

Artifacts: `/tmp/lab-code-search-workers-{after,control,repeat,concurrent,two-single,retained,retained-concurrent}-{http,server}.json`;
`/tmp/lab-code-search-workers-concurrent-{control-fixed,two-fixed,one}-{http,server}.json`;
retained failed `workers-concurrent-{control,two}` reports/logs;
`/tmp/lab-code-search-workers-{comparison,reusable,summary}.json` and logs;
`/tmp/lab-code-search-{read32,read1m}-{http,server}.json`;
`/tmp/lab-code-search-workers-retained-tests.log`.

The Code Search UI remains a placeholder; this checkpoint is backend work.
The goal remains open for simultaneous searches, other expensive regex/corpus
combinations, cold UI/terminal creation, terminal output typing tails, broader
UI/API coverage and physical/iTerm parity. Main merge remains pending after
the earlier automatic approval rejection; no merge, push or live-server restart
was attempted.

## Decode complete search output after releasing capture chunks

Code search now collects stdout and stderr through the original subprocess
pipes as bytes on POSIX, then decodes both complete streams in their original
order. Returning from the runner releases intermediate pipe chunks before text
allocation. Most output contains no carriage return, so a fast check avoids
the two full-string universal-newline replacement scans. Output containing CR
still receives the original CRLF-to-LF and CR-to-LF transformations.

This uses public APIs, not a replacement collector or private subprocess hook.
Encoding is selected before launch using
[`io.text_encoding(None)`](https://docs.python.org/3.14/library/io.html#io.text_encoding),
which honors UTF-8 mode and opt-in EncodingWarning. Its `locale` result is
resolved through [`locale.getencoding()`](https://docs.python.org/3.14/library/locale.html#locale.getencoding).
The measured interpreter uses UTF-8 mode even though the underlying locale is
ASCII; substituting locale encoding alone would break Unicode results. Python
3.11 is the repository's minimum, and supports these APIs. Non-POSIX keeps the
original text-mode runner, including its existing capture/error behavior.

Both pipe EOFs and process completion are still required. Nothing stops or
truncates the command at the response limit. Strict decoding still examines
all stdout and stderr, preserves the original error bytes/offsets/reason, and
reports stdout decoding failures before stderr failures. Timeouts still discard
partial results and reap the direct child. No worker policy, search arguments,
result parsing/order, Git fallback or API completion semantics changed.

### Complete HTTP comparison

The unchanged 5,000-file/100,000-match fixture uses normal authenticated server
lifespan and polling, checks 100 unique valid rows and exact snippets in every
response, then commits and finds a fresh Unicode result. Two clients are released
together each round. Every first response and failure remains included.
Only `code_search.py` was restored to `e35ae0a` for the later original control.

| Two-client run, 40 requests each | First pair maximum | Overall maximum | Median | Misses >=200 ms | Fresh query |
| --- | ---: | ---: | ---: | ---: | ---: |
| Original, coarse diagnostic timers | 262.68 ms | 262.68 ms | 183.96 ms | 6 / 40 | 48.57 ms |
| Prototype, coarse diagnostic timers | 214.95 ms | 214.95 ms | 147.65 ms | 2 / 40 | 45.45 ms |
| Production candidate, unprofiled | 209.27 ms | 218.85 ms | 141.51 ms | 4 / 40 | 45.58 ms |
| Restored original, unprofiled | 288.19 ms | 288.19 ms | 182.07 ms | 2 / 40 | 45.82 ms |
| Restored candidate repeat, unprofiled | 197.37 ms | 197.37 ms | 139.41 ms | 0 / 40 | 44.74 ms |

The two unprofiled candidate runs passed **76/80 requests**. The earlier four
misses are not superseded by the passing repeat; simultaneous search is still
not guaranteed below 200 ms. In fact, the candidate and restored control have
the same 5% miss rate when these small unprofiled samples are pooled, despite
the candidate's substantial median/headroom improvement. The result is an
incremental improvement, not completion of the overall target.

A separate single-client candidate run passed 20/20 requests: median
**109.58 ms**, first/maximum **171.17 ms**, fresh query **47.92 ms**. All 220 timed
responses and six fresh reads in the table plus single-client run passed content
verification; all six servers stopped and their fixture roots were removed.
The coarse diagnostic showed median parent-thread CPU falling from 70.89 to
49.22 ms per large search; prototype decoding used a median 5.43 ms CPU. These
coarse phases are nested, not additive timing totals.

### Allocation evidence

A separate owned child emitted the exact 27,455,000-byte synthetic result into
the original and candidate capture paths in two alternating pairs. Every full
stdout hash, length, stderr, argument list and return code matched. Tracemalloc
was stopped before hashing; these measurements are Python allocation evidence,
not latency or total-process-RSS measurements.

| Capture path | Peak traced bytes, pair 1 | Peak traced bytes, pair 2 |
| --- | ---: | ---: |
| Original text capture | 82,403,439 | 82,402,832 |
| Decode after binary capture | 55,013,887 | 55,013,903 |

Peak capture allocations fell by about **27.39 MB (33%)** while the retained
output stayed about 27.46 MB in both versions. Child-process and OS memory are
outside this measurement. The owned child completed and its fixture was removed.

### Verification and diagnostic limits

**259 focused checks passed**. Native comparisons with the original text runner
cover UTF-8, ASCII, Latin-1 and UTF-16LE; empty, mixed-newline and large output;
zero/nonzero return codes; invalid stdout/stderr/both; and exact decoding-error
identity, including the complete offending bytes' hash and offsets. Fresh
interpreters exercise UTF-8 mode on/off and EncodingWarning on/off. Additional
checks cover encoding selection before launch and fresh selection on the next
call, the non-POSIX fallback, delayed descendant stdout and stderr, and timeout
cleanup even when partial output is invalid. Existing parser, worker-policy,
repository, Git-invocation and search-route checks remain included. Python
compilation and `git diff --check` passed. Older broad-suite baseline failures
remain separate.

An earlier per-request cProfile attempt failed one concurrent request with
`ValueError: Another profiling tool is already active`. A nonblocking profiler
guard allowed both requests to proceed, but yielded inconsistent function data
(for example, poll self time 87.83 ms versus cumulative time 2.13 ms). Those
function costs were rejected as evidence. The guarded diagnostic retained
14/40 HTTP misses, maximum 582.81 ms; its profiler-perturbed timings are not a
passing latency claim. Both diagnostic servers stopped, and a final filesystem
inventory found no remaining owned HTTP fixture roots. Raw failures and timings
are preserved.

Artifacts: `/tmp/lab-code-search-{binary-control,binary-after}-{http,server}.json`;
`/tmp/lab-code-search-decoding-{after,control,repeat,single}-{http,server}.json`;
`/tmp/lab-code-search-decoding-{summary,memory}.json`;
`/tmp/lab-code-search-decoding-memory.py` and log;
`/tmp/lab-code-search-capture-profile{,-fixed}-{http,server}.json` and logs;
`/tmp/lab-code-search-decoding-retained-tests.log`.

The Code Search UI remains a placeholder; this is backend evidence. The full
objective remains open for retained search misses, other corpora/regexes, cold
UI and terminal creation, terminal output typing tails, broader UI/API coverage
and physical/iTerm parity. Main merge remains pending after the earlier automatic
approval rejection; no merge, push or live user-server restart was attempted.

## Assistant note listings reuse one fresh snapshot (2026-09-23)

The Assistant endpoint rebuilt `records.records(root)` for every plain note's
descendant search text. The embedded-document cache does not make this free:
each call fingerprints all files and deep-copies the rows. An owned fixture
with 100 notes and 20 embedded subtabs performed **108 snapshots per response**.
Whole-snapshot diagnostics attributed about 2,429 ms of the four original
responses' combined 2,501 ms HTTP time to those calls.

`assistant_v2.plain_note_rows` now loads one local snapshot and uses it for all
eligible notes and descendants. The complete endpoint performs **eight snapshots**;
other consumers remain unchanged. No response cache, watcher/polling change,
prewarming or early response was added. Existing descendant order, all row
fields, note-type and embedded filters, path validation and string conversion
remain intact. Every subsequent request still checks fresh files.

### Complete HTTP reads

`scripts/perf/lab_assistant_latency.py` creates its vault through Lab, initializes
and migrates an owned Assistant root through the normal storage functions, and
creates real notes and subtabs. It uses authenticated HTTP, normal server
lifespan and polling. Initialization's process-local snapshot is discarded so
the first measured request reads the fixture itself. Every response validates
all note identities, paths, titles, bodies, summaries, stars, attributes and
descendant search text, along with document/task fields and dashboard sections.
Repeated unchanged responses must have identical complete hashes. A final
Markdown edit must appear immediately in both notes and document search text.
Every first sample and failure is retained.

| 100-note HTTP run | First | Median of unchanged reads | Maximum, including fresh read | Misses >=200 ms | Fresh edit |
| --- | ---: | ---: | ---: | ---: | ---: |
| Original, 20 reads + edit | 636.18 ms | 614.99 ms | 657.04 ms | 21 / 21 | 633.09 ms |
| Candidate, 20 reads + edit | 77.29 ms | 55.66 ms | 77.29 ms | 0 / 21 | 72.38 ms |
| Original, coarse snapshot diagnostic, 3 reads + edit | 643.62 ms | 616.56 ms | 643.62 ms | 4 / 4 | 626.59 ms |
| Candidate, coarse snapshot diagnostic, 3 reads + edit | 78.34 ms | 56.49 ms | 78.34 ms | 0 / 4 | 64.35 ms |

All 50 responses passed content checks. These are single-client complete
endpoint measurements, not physical display timing or a concurrent-client
guarantee. All four servers stopped and their fixture roots were removed.

### Native Dashboard, All, Starred and workspace navigation

The reusable `--assistant` workflow adds native Chrome clicks to the existing
isolated navigation harness. Each of 20 cycles enters Assistant, switches to
All, switches to Starred, then returns to an alternating workspace. Every
displayed card must have the correct path, kind, title, summary, star state and
empty-task badge. Dashboard checks include section order, item limits and
overflow counts; full lists check all matching rows. The probe compares every
Markdown file after each cycle. It does not open an Assistant API warm-up,
mock fetch, change polling, or exclude cold clicks.

All three full runs used the same 100-note/20-subtab workload, 5,000 mixed files
and 2,500 Git changes **per workspace**, a fresh browser profile and normal
server lifespan. The entire Git result and rendered decorations were verified.

| Native run, 80 clicks each | Assistant first | Assistant browser p50 | Assistant maximum | Assistant misses / 20 | View-switch maximum / 40 | Workspace-return maximum / 20 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Original | 967.8 ms | 831.3 ms | 1,563.5 ms | 20 | 40.4 ms | 237.1 ms |
| Candidate | 115.2 ms | 148.7 ms | 232.4 ms | 2 | 39.6 ms | 185.7 ms |
| Candidate repeat | 212.1 ms | 165.6 ms | 242.5 ms | 2 | 39.4 ms | 156.5 ms |

The candidate passed **36/40 Assistant entries** and **120/120 other clicks**.
Four Assistant misses remain: 231.7, 232.4, 212.1 and 242.5 ms. The repeat's
cold miss remains included. Native input timestamps, clock validation and a
render opportunity define these numbers; they do not establish physical
input/display latency. The original also missed its first workspace return.

The candidate runs retained 1,018 browser API requests with two >=200 ms
responses, and 1,069 ASGI requests with two misses (maxima 200.26 and 220.41 ms).
All returned successfully, with no browser errors or failed requests. The
original retained 27 misses among 462 browser requests and 27 among 488 ASGI
requests. Request counts differ because normal polling continues during the
different elapsed runtimes; no poll or request was removed from the workloads.
The first candidate's slow clicks included Assistant responses of 200.8 and
194.2 ms, so the isolated 56 ms median is not a universal service-time bound.

The original small smoke run retained two slow Assistant entries (763.7 and
870.2 ms) and three API misses. An additional candidate probe with the minimum
two-note fixture passed all eight clicks, all 63 browser requests and all 89
ASGI requests; it verifies singular Starred counts as well as the file-backed
fixture manifest. These small runs do not replace the loaded comparison.

### Correctness and remaining work

The 16 new regression cases span split-file schema 2, embedded subtabs, unified
storage and document tasks. They compare the old and new complete note rows
and full endpoint responses, assert one local listing read, preserve nested
descendant order, and verify edits, additions, deletions, caller mutation
isolation and symlink rejection. Existing Assistant route/storage/dashboard,
task/meeting, metadata, query and frontend checks were included.

With browser access, **189 checks passed and one failed**. The failing
`test_custom_attributes_browser` times out saving an attribute. Restoring the
original endpoint reproduced the same failure; the candidate was restored
after that control. A prior sandbox-only run passed 181 checks but could not
launch Chrome for nine tests. Those startup failures are retained separately.
The strengthened full-response regression checks then passed all 16 cases.
Python parsing, Node syntax checks and `git diff --check` passed.

All five native fixture servers stopped. A final process/directory inventory
found no remaining owned navigation/Assistant benchmark processes or fixture
roots. No user tmux sessions, live user server, main-checkout files or user
Assistant documents were changed.

Reproduce with the checkout's Python environment:

```sh
python scripts/perf/lab_assistant_latency.py --notes 100 --samples 20 --output /tmp/assistant-http-new
python scripts/perf/lab_navigation_latency.py --assistant --samples 20 --extra-files 5000 --extra-file-types md,py,json,sql --git-changes 2500 --server-timings /tmp/assistant-native-new-server.json > /tmp/assistant-native-new-browser.json
```

Artifacts: `/tmp/lab-assistant-{before,after}{,-trace}-{http,server}.json` and
logs; `/tmp/lab-assistant-native-{smoke,before,after,small,repeat}-{browser,server}.json`
and logs; `/tmp/lab-assistant-{summary,cleanup}.json`;
`/tmp/lab-assistant-focused-tests{,-native}.log`,
`/tmp/lab-assistant-attributes-original.log` and
`/tmp/lab-assistant-note-listing-final.log`.

The overall goal remains open: native Assistant entry still has four retained
misses, the endpoint has eight snapshot consumers, and prior search, cold UI,
terminal creation/typing tails and physical/iTerm parity gaps remain. Main merge
remains pending after the earlier automatic approval rejection; no merge, push
or live-server restart was attempted.
