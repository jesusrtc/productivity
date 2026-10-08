# Dismiss completion with two separate clicks

Superseded by [terminal output quiet period and review](terminal-output-quiet-period-and-review.md):
only the continuous viewing interval or direct green-dot activation acknowledges
a result. Tab clicks do not acknowledge it and double-click opens Rename.

Besides the configurable viewing delay, dismiss a terminal's completed-response
green dot by clicking its tab, keeping it selected, then clicking it again at
least two seconds later. Wait one second after the candidate second click so a
double-click can cancel it. Double-click still opens Rename and never manually
acknowledges the response, even after an earlier selection.

Switching tabs, losing focus/visibility/connection, a newer response, or new work
resets the click sequence. Clicks before completion do not count. A pending
click must recheck the exact response and current visible connection before
acknowledging it. Keep this acknowledgement browser-local like the timed path.
