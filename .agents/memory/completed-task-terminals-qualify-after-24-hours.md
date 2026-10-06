# Completed-task terminal cleanup starts after 24 hours

Completing an Objective task records completed_at as Unix seconds. Repeating
Completed preserves the original time; reopening, pausing or declining clears
it. Do not invent timestamps for legacy completed tasks.

Reviewed Resources cleanup can delete a task’s primary terminal after strictly
24 hours from completion and 24 hours without terminal use/access. This is
cleanup eligibility, not an automatic background kill. Offer the cleanup view
from the terminal menu. Fixed workflow/Objective mains, connected terminals,
working/waiting agents, managed servers and unsent document drafts are excluded.
Other terminals retain the seven-day inactivity rule. Include task identity and
completion time in candidate fingerprints; recheck task/main state under the
Objective read lock before the exact tmux freshness check and kill. Preserve
provider conversations and use isolated sockets/fixtures for destructive tests.
