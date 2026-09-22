# Terminal completion uses the blinking green vertical line

For Codex, Claude, and Copilot, reuse the existing left-edge green vertical
line as the ready-to-review signal. A steady line means recently selected;
a blinking line means a verified completed response is unread. There is no
separate blue dot. Use the same 3px line and configured recent-marker color,
with a slow on/off blink and slight glow. Keep it visible on the selected tab
until its response is acknowledged. Reduced motion uses a steady glow.

Stop blinking only after 20 continuous seconds viewing that completed response.
Clicking alone must not acknowledge it. The selected terminal must remain
visible and connected in the focused Lab window. Switching terminals,
hiding/collapsing the panel, losing focus, disconnecting, or reloading resets
the interval. A newer response always starts its own interval. Hovering never
acknowledges it. After acknowledgement, normal recent-line behavior resumes.

Configure the delay in Settings → Global → Terminal appearance → Stop blinking
after viewing (seconds). Default 20; valid range 1–3600; save browser-wide.
Confirmed unread completions and acknowledgements survive refreshes, but
partially elapsed viewing time does not. Unknown state never creates a signal.

Copilot emits assistant.turn_end between tool batches too. Require a text
assistant.message with no toolRequests followed by the matching turn_end;
ignore child-agent events. Claude turn_duration can follow interruptions, so
it is not sufficient evidence. Codex uses the live TTY-to-thread mapping and
successful task_complete events, never a stale saved conversation ID.

Keep transcript reads bounded/cached and confined to scoped terminal lists.
See docs/terminal-completion.md and core/agent_activity.py for the contract.
