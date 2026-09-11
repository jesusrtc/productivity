# Terminal hover stays left and shows only the latest request

Session hover shows only the last user request, without older requests,
objectives, linked-file identity, or session metadata. The selected session's
header keeps its full context history.

Place the tooltip entirely left of the terminal panel, alongside the hovered
tab. Constrain its width to that space; hide it if there is no usable left margin.
Never flip it above, below, or inside the terminal. Clicking a tab dismisses it.
This supersedes the five-item hover policy in terminal-task-summary-is-multiline.md.
