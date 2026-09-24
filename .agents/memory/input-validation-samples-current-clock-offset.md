# Validate native input against a current wall/monotonic clock pair

CDP accepts Unix-epoch input timestamps, while DOM event and performance times
use a monotonic clock. Do not assume performance.timeOrigin + event.timeStamp
will equal the dispatched wall-clock epoch throughout a long run. Their offset
can drift as wall time changes.

The shared scripts/perf/input_clock.mjs captures Date.now() between two
performance.now() reads in the event handler. Validate the dispatched epoch with
that current pair, preserving the raw origin-based delta. Reject missing/nonfinite
values, sampling brackets wider than 1 ms, and mapped deltas beyond 2 ms.
Durations still subtract the original event.timeStamp from handler/parse/render
times, including all queued input; never adjust a latency or widen its budget to
make validation pass. The native Chrome regression deliberately blocks the
renderer and sends wrong timestamps to verify both properties.

See Chromium's GetEventTimeTicks in content/browser/devtools/protocol/input_handler.cc
and the W3C High Resolution Time clock-drift discussion. Earlier reports without
the clock-pair samples cannot be retroactively validated by this method.
