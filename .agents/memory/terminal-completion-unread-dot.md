# Terminal completion is an unread blue dot

The user wants a completion signal for all three terminal agents: Codex,
Claude, and Copilot. Keep it separate from the green recently-used vertical
line. The blue dot appears only after a verified main-agent response boundary
and clears only after 20 continuous seconds viewing that completed response.
Clicking alone must not clear it. The selected terminal must remain visible and
connected in the focused Lab window. Switching terminals, hiding/collapsing the
panel, losing focus, disconnecting, or reloading resets the interval. A newer
response always starts its own interval. Hovering never clears the dot.

Make the delay configurable in Settings → Global → Terminal appearance →
Clear blue dot after viewing (seconds). Default 20; valid range 1–3600 seconds;
save browser-wide alongside the other terminal appearance preferences.
Confirmed unread completions and acknowledgements survive refreshes, but
partially elapsed viewing time does not. Unknown state never creates a dot.

Copilot emits assistant.turn_end between tool batches too. Require a text
assistant.message with no toolRequests followed by the matching turn_end;
ignore child-agent events. Claude turn_duration can follow interruptions, so
it is not sufficient evidence. Codex uses the live TTY-to-thread mapping and
successful task_complete events, never a stale saved conversation ID.

Keep transcript reads bounded/cached and confined to scoped terminal lists.
See docs/terminal-completion.md and core/agent_activity.py for the contract.
