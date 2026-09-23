# Include input waiting for the browser main thread

Timing from inside a keyboard/click handler misses time queued before dispatch.
Use `scripts/perf/lab_navigation_latency.py --typing --samples 100` for a disposable
CLI-created vault, normal UI polling, and an owned raw-echo terminal. The probe
timestamps native CDP keys from Node, verifies `Event.timeStamp` against the sent
epoch, and sends keys without waiting for renderer acknowledgments. It retains
every key, including first input, checks exact echoed text through wrapped lines,
and reports queue, parse, and xterm render timing. tmux's status line is excluded
by reading only through the app cursor, not by dropping unexpected characters.

The second phase deliberately calls sidebar refresh every 500 ms. Label that
load as controlled; do not imply production always refreshes at that frequency.
Use `--extra-files 5000 --extra-file-types md,py,json,sql --extra-file-layout flat`
to expose interference from a large sidebar. CPU/timeline profiling is optional;
retain unprofiled final results, failures, and the empty-page frame control.
Physical keyboard and display scanout remain outside these measurements.

Navigation clicks now use the externally supplied mouse-release timestamp too.
The older `lab_terminal_latency.py --browser` synthetic probe uses `ui_check=1`
and starts inside the browser; its earlier passing results do not establish
typing responsiveness during normal polling or main-thread queueing.
