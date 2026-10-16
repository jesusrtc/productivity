# Inactive task terminals expire automatically

The user requested automatic quota cleanup on October 16, 2026. The default bar
shows task terminals only for In progress; explicit Show all still inspects
inactive sessions. Completed, Won’t do and Undo/Todo get one hour after the
status transition; Paused gets three days. Check every minute across registered
vaults even with no browser. Reactivation cancels expiry, a different status
restarts it, and repeated identical status saves preserve the timestamp.

Saved children inherit parent task ownership; their own task takes precedence.
Persist automation ownership in backend launches and browser hierarchy changes
for independent cleanup. Recheck task state under its lock and match the exact
tmux incarnation atomically. Status retention intentionally expires attached or
busy sessions too. Exclude fixed mains, managed servers, shared document processes
and unrelated terminals. Keep saved conversation IDs, task links and parent
ownership; suppress automatic restore with a persisted retirement marker until
explicit reopen. Unknown historical transition times receive a full grace
period on first observation, retained in the vault runtime journal.

Assistant task links follow equivalent statuses, with Blocked using the Paused
window. Admin GET/POST `/api/term/task-cleanup` inspect/run the policy, exposed via
`lab api`. `LAB_TASK_TERMINAL_CLEANUP=0` disables the worker and is mandatory in
ordinary test fixtures. Real tmux tests always use private sockets.

This automatic policy supersedes the older 24-hour completed-task retention
guidance; the Resources reviewed inactivity cleanup remains a separate action.
