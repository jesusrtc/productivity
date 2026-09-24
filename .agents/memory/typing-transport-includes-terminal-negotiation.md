# Distinguish terminal-query replies from typed keys in transport probes

The terminal WebSocket carries xterm's automatic terminal-query replies as
`input` messages in addition to actual keys. Do not require every outgoing input
frame to match the native key count. The isolated typing probe records all owned
socket frame metadata, then validates its one-letter fixture keys separately.
Keep startup negotiation frames in diagnostics; never drop slow measured keys.

CDP frame timestamps plus external key, handler, parse and render timestamps can
separate a missing echo frame from a browser parse/paint delay. Only observe the
owned disposable terminal and retain metadata (type/length/time/resize geometry),
not payloads or credentials. A prompt input frame with a much later echo does not
by itself identify which server/PTY/tmux/network component caused the delay.
