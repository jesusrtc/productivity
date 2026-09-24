# Terminal detach drains tty output before closing

On the measured macOS/tmux 3.6a setup, immediate PTY master close during pane
eviction caused tmux itself to block in `server_client_lost → close`. The next
`has-session` command took about 535–541 ms, and terminal switches took about
680 ms. Lab's own PTY close and fork were fast; browser disposal was not the
main cost. A native tmux stack sample identified the blocked close.

After both WebSocket/PTY pumps stop, run `_term_stop_pty` on a worker. Signal
only the owned attach child, nonblockingly drain final output for at most
100 ms, then close/reap as before. This must never send input or kill the tmux
session. EOF, EIO, a missing child, a bad fd, silence and continuous output must
all release resources without blocking the event loop.

Keep the browser cache limit (three parked panes plus active) unchanged. The
native `--terminal-tabs` fixture uses six owned sessions, verifies rendered
contents/focus and preserves typed characters across warm switches and actual
evictions. `--typing-detaches` adds another owned attach/detach workload during
the loaded typing phase. PTY timing removes fd ownership before close so a
concurrent fd reuse does not erase the new connection's trace association.
