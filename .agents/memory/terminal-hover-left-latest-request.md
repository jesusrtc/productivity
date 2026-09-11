# Terminal hover stays left with enough recent request context

Start the hover preview with the latest user request. If it is shorter than
50 characters, prepend previous requests until their combined text reaches
50 characters or the history is exhausted. Display the result chronologically,
one request per line. Keep the selected session header's full request history.

Both the hover and the request section show a colored project → worktree →
linked file identity header. Use configured project/worktree colors and omit
unknown identity parts rather than inventing links or worktrees.

Place the tooltip entirely left of the terminal panel, alongside the hovered
tab. Constrain its width to that space; hide it if there is no usable left margin.
Never flip it above, below, or inside the terminal. Clicking a tab dismisses it.
This supersedes the five-item hover policy in terminal-task-summary-is-multiline.md.
