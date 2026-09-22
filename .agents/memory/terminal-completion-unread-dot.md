# Terminal completion is an unread blue dot

The user wants a completion signal for all three terminal agents: Codex,
Claude, and Copilot. Keep it separate from the green recently-used vertical
line. The blue dot appears only after a verified main-agent response boundary
and clears immediately when the user clicks the terminal tab or the dot, even
while navigation or reconnecting is pending. Keyboard activation does the same.
Automatic acknowledgement still requires a visible, connected terminal in the
focused window. Hovering must not clear it. Confirmed unread completions and acknowledgements
survive refreshes; unknown state never creates a completion signal.

Copilot emits assistant.turn_end between tool batches too. Require a text
assistant.message with no toolRequests followed by the matching turn_end;
ignore child-agent events. Claude turn_duration can follow interruptions, so
it is not sufficient evidence. Codex uses the live TTY-to-thread mapping and
successful task_complete events, never a stale saved conversation ID.

Keep transcript reads bounded/cached and confined to scoped terminal lists.
See docs/terminal-completion.md and core/agent_activity.py for the contract.
