# Disposable Lab fixtures still use the default tmux generation

The navigation fixture uses a fresh temporary LAB_HOME and unique session-name
prefix, but does not seed a tmux generation. With no tmux-sockets.json,
lab.tmux_sockets.default_state() selects the default socket. Its HTTP server,
browser and sessions are owned; an already-running default tmux server is shared.
This also applies to the historical terminal latency benchmarks.

Do not kill/restart the default server, trace other sessions, or silently replace
these measurements with a quieter transport. If testing a fully owned tmux
server, label it as a separate diagnostic, route only temporary configuration,
verify ownership before cleanup, and retain the ordinary/default-server results.
The slow scrolling-output writes may overlap shared tmux scheduling, but this
is an unproven cause until a controlled comparison separates it.
