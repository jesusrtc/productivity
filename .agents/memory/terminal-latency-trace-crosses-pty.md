# Trace terminal latency across the PTY boundary

The isolated fixture's `--trace-terminal --server-timings <path>` records metadata
at browser socket, ASGI receive/send, term.py PTY read/write, and owned echo-process
read/write. No payloads or credentials are recorded. Module-local os/pty proxies
must preserve short writes/errors, track only descriptors created in a traced
connection, forget closed descriptors, and restore dependencies on exit.

The echo process keeps timestamps in memory and exports only after measurement.
Verify its recorded PID still owns the unique benchmark pane before signaling;
terminal cleanup must run even when export fails. Coalesced reads can represent
multiple keys, so compare byte counts rather than requiring one event per key.

A prompt WebSocket send does not prove prompt PTY delivery, and a prompt parse
does not prove prompt render. Preserve external source, handler, parse and render
timestamps and all over-budget keys. A gap between PTY write and read narrows the
investigation but does not alone distinguish tmux, application or descriptor-read
scheduling. The fixture's default socket may share a tmux server with other work;
it only owns its generated terminal, never other sessions or the default server.
