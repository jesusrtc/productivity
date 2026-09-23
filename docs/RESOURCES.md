# Host resources

The admin-only **Resources** button in the top bar shows host CPU, memory and
swap, followed by Lab-related processes sorted by CPU or resident memory. The
panel refreshes every three seconds while visible. The first sample establishes
a CPU baseline; process CPU uses 100% per logical core, while host CPU is 0–100%.
Resident memory can include shared pages in more than one process.

Process ownership comes from the current Lab server and panes in Lab-named tmux
sessions on the configured active/draining sockets, then their descendants.
Verified descendants remain tracked by PID and creation time while alive, even
if they detach. Generic Python, Node, Jupyter, browser and other unrelated host
processes are not selected by executable name or working directory. Detached
processes that were never observed under Lab are not discovered. Tracking is
in memory and resets when Lab restarts.

**Stop** sends SIGTERM to the selected process. **Force kill** sends SIGKILL.
Both require confirmation, recheck ownership and creation time on the server,
and target one process rather than a process group. Lab's server and shared tmux
transport are protected. Stopping a kernel loses its in-memory variables;
stopping an agent can interrupt work. Managed services may restart themselves;
use their normal server controls to keep those services stopped.

**Pause file scans** cancels Files-view scans cooperatively, clears their queued
work, and prevents polling from starting replacements. Completed file listings
remain available. **Resume file scans** allows normal requests to reconcile the
files again. The pause is global to this Lab server, in memory, and resets on
restart. It does not pause vault indexing or native filesystem notifications.
A scan stuck in an OS filesystem call can exit only when that call returns.

The APIs are `GET /api/resources`, `POST /api/resources/stop` (PID, creation time,
and `stop` or `kill` action), and `POST /api/resources/scans` (`paused` boolean).
They require an authenticated Lab administrator. Monitoring never starts a
notebook, allocates a terminal, or initiates a file scan.
