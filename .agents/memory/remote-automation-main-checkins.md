# Remote automation check-ins belong to the main

On October 20, 2026 the user requested a yellow check-status notification every
30 minutes for automations running over SSH or similar connections, main only.
Scope check-ins to SSH/nested tmux and detected SSH/tmux/mosh descendants, using
existing local owned process reads. Ordinary local-only recipes do not alert.
Aggregate child connections at their closest automation main, including existing
parents and nested automation groups. Start a new window on launch/renewal.

Keep the real agent report and status dot intact. This requests a manual status
check; connection liveness does not establish remote job health or completion.
Never replay recipes or execute new remote/health probes to create a reminder.
Persist the latest check-in with the main incarnation, resolve known ended
connections, preserve uncertainty on failed reads, and retain exact navigation,
history and Snooze 30 min only. A full snooze spans recurring check-ins from
the same launch but cannot hide another launch or real input request.
