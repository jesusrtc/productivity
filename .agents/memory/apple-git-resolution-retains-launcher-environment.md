# Apple Git resolution retains the launcher environment

On the measured Mac, PATH selects `/usr/bin/git`, Apple's developer-tool
launcher. The Git binary selected by `xcrun --find git` took about 4.9 ms for a
small command versus 10.6 ms through the launcher. Python's final process wait
was only about 0.006 ms; disabling subprocess timeouts did not remove the cost.

The repository-list endpoint resolves the executable once per request only
when PATH selects that exact Apple launcher. It also obtains the environment
through `xcrun /usr/bin/env -0`: directly using the binary without this changed
CPATH, LIBRARY_PATH, MANPATH and SDKROOT in a controlled comparison. Keep both
the selected executable and full launcher-prepared environment request-local.
Never log or return the environment. Resolve each request afresh, preserve
custom PATH installations/wrappers and other platforms, and fall back to the
ordinary launcher on discovery or selected-tool execution failure. Keep the
original command arguments, timeouts and Git result parsing.

Two-client catalog checks exposed misses hidden by single-client timing.
The final two eight-worker runs passed 80 concurrent requests, but an earlier
resolved-Git run retained a 208.8 ms miss. Increasing the worker limit was not
retained. The benchmark records all clients, releases each round together,
verifies overlapping complete requests and every stable metadata field, and
keeps the first pair plus a fresh branch/commit check. See performance-progress
for the full comparisons and remaining scope; these are HTTP, not UI timings.
