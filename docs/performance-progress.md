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
