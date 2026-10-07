# Automation recovery only for stopped work

The user requested on October 7, 2026 that automation terminals offer a relaunch
button only when their launched process, SSH connection or nested tmux client
has ended/disconnected. Parent terminals should relaunch all stopped descendants
together and leave running children alone. Recovery is explicit, never automatic.
Check current TTY-scoped liveness again before respawning an idle pane and reject
stale launch generations or duplicate requests. Preserve tab identity and old
output. A live SSH session cannot reveal apps manually started inside it; optional
background health checks must distinguish running (0), stopped (1), and unknown.
