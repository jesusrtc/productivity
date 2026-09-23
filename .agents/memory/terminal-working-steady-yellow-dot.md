# Working agents use a steady yellow dot

Codex, Claude, and Copilot terminal tabs show a fixed yellow dot while their
recorded agent state is working. The user explicitly corrected blinking yellow
to steady yellow: only the finished/ready-to-review green dot should blink.
Hover and the accessible tab label say Working. Clear the dot on the next
refresh for any non-working state; hide it for unreachable terminals. It has
no acknowledgement delay. Keep the configurable 20-second viewing delay for
the separate completion signal.

Reuse the scoped, cached provider activity data. Copilot resume/context events
alone are not work; resume clears stale in-flight state. Claude turn_duration
clears unfinished working state without manufacturing a completion. Preserve
confirmed completions across those idle events. See docs/terminal-completion.md.
