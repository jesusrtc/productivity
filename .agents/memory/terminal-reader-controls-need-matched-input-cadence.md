# Terminal reader controls need matched input cadence

A private-PTY A/B/B/A initially suggested large producer-write gains from a
dedicated blocking reader thread. Its foreground `sleep` scheduled inputs up
to 10.12 ms late versus 2.17 ms with the selector, despite the same nominal
25 ms cadence. That is a confounded result, not a transport improvement.

Capping both waits at 1 ms kept actual dispatch lateness below 0.61 ms, but
producer stalls remained. A nonblocking reader-thread repeat did not establish
a consistent gain either. No reader-thread production candidate was retained.
Private component controls also lack browser/xterm rendering, polling and Git
updates; they cannot replace native typing-to-render checks.

After `tmux kill-server`, wait boundedly for both the owned producer and the
owned private server to exit before deciding cleanup failed or unlinking the
recorded socket inode. One diagnostic stopped on that exit race; preserve its
failure and independently verify recorded PIDs before removing its stale socket.
