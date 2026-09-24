# Batch terminal setup with individual failure recovery

_configure_tmux_wheel_scrolling sends its four existing commands in one tmux
client invocation: session mouse on, alternate-screen off, the guarded
WheelUpPane binding, and removal of root WheelDownPane. Keep their exact values,
order, captured socket and child environment. This cuts repeated client-process
startup in the creation endpoint without changing terminal input/output.

A semicolon-separated tmux sequence stops after its first failing command.
On nonzero exit, retry the four idempotent commands individually, preserving the
old best-effort continuation when a session exited or an option failed. This
rare path can make five calls. Do not omit the fallback to save failure time.
The real-tmux test uses a private temporary server and verifies correct bindings
after a missing-session failure, unrelated-session options and server exit.

Matched native medians: setup 30.60→8.21 ms, creation endpoint 66.13→45.07 ms,
creation click 204.8→188.3 ms. A 40-creation run without function tracing had a
183.7 ms median but retained seven >200 ms misses, including a 298.2 ms first
creation. These results do not establish universal latency or typing parity.
