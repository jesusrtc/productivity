# Completed agents use a blinking green dot

Codex, Claude, and Copilot use one status dot beside each terminal tab:
steady yellow while working; blinking green when a verified completed response
is ready to review. The left-edge vertical line indicates recency only and
never blinks. The completion dot uses green independently of the configurable
recent-marker color. Both dots use the same size and position. New work takes
priority over an older unread completion, so only one dot appears.

Keep the green dot on the selected tab until acknowledgement. Reduced motion
uses a steady glow. Automatically dismiss after 20 continuous seconds selected,
visible, connected, and focused, configurable from 1–3600 seconds in Settings →
Global → Terminal appearance → Stop blinking after viewing (seconds). Leaving,
switching, disconnecting, reloading, or a new response resets the interval.
Hovering never acknowledges it. Confirmed unread responses and acknowledgements
persist across refreshes. See terminal-completion-second-click.md for the
manual shortcut.

Copilot turn-end events also follow tool batches: require a text message with
no toolRequests followed by its matching turn_end. Claude turn_duration alone
is not completion. Codex uses a live TTY-to-thread match and task_complete,
never a stale saved thread ID. Keep transcript reads bounded/cached and limited
to scoped terminal lists. See docs/terminal-completion.md.
