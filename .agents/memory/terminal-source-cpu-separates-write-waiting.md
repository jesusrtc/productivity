# Producer CPU separates computation from waiting during terminal output

Output typing's optional `--trace-terminal` diagnostics include `threadCpuMs`
for each whole source batch and input-footer write. Untraced runs do not call
the CPU clock or add these fields. Real-PTY tests verify both paths alongside
exact input hashes, resizing and live-after-report cleanup.

Native diagnostics found a shared 35.057 ms source write using 0.037 ms CPU,
and a private 22.398 ms write using 0.098 ms CPU. Most elapsed time was not
producer computation. This does not name the waiting/scheduling mechanism or
explain every browser delay.

An A/B/B/A component check also reproduced long writes through owned private
tmux without a browser/WebSocket, while direct PTY writes stayed below 0.35 ms.
This control has no xterm negotiation, rendering, Lab polling or Git workload;
it cannot replace native timing. Separately increasing attachment or producer
virtual baud to 115,200 did not improve the slow-write distribution. Neither
setting was changed in production. See docs/performance-progress.md for all
results, limitations and retained artifacts.
