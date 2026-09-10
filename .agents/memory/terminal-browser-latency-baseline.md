# Terminal latency needs a browser frame baseline

Fast PTY/WebSocket echo alone does not establish responsive typing. Use
`core/.venv/bin/python scripts/perf/lab_terminal_latency.py --browser` to
measure synthetic keyboard events through Lab's real input handler, transport,
xterm parsing, and render callback in a disposable authenticated browser.
The wrapper creates, replaces, and removes only its own unsaved test terminal.
It never attaches to or sends input into a user's existing terminal.

The same run measures requestAnimationFrame cadence on an empty page. When
both Lab and that control page have long frame delays, investigate host/browser
scheduling before changing xterm or removing UI features. These measurements
exclude physical keyboard hardware and display scanout. Optional
`LAB_PERF_CPU_PROFILE=/tmp/trace.cpuprofile` records a Chrome CPU profile;
profiling itself can affect timings, so use an unprofiled run for final numbers.

Endpoint latency tests use the raw authenticated TestClient after one initial
index materialization. Functional tests' per-request index rebuild is a test
convenience, not part of the live server request path, and must stay outside
endpoint timing samples. Keep existing latency thresholds unchanged.
