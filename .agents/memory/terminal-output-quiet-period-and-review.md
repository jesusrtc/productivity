# Terminal output quiet period and review

The latest [tab-click correction](green-terminal-dot-clears-on-tab-click.md)
supersedes timed viewing dismissal and removes the delay setting. The 40-second
output detection rule below remains applicable.

On October 8, 2026 the user requested activity detection from terminal output:
steady yellow for changes in the last 40 seconds, then blinking green after
40 seconds of quiet. Apply it to all visible terminal types, including child
processes and merged tabs. Reuse tmux's output timestamp in the existing batched
listing; do not add per-terminal capture polling. Quiet means ready to review,
not that a task or its authoritative checklist has been completed.

Green clears only after the configurable continuous active viewing interval
(20 seconds by default, visible/connected/focused), or direct green-dot review.
Tab clicks and double-clicks do not acknowledge it; double-click opens Rename.
Preserve acknowledgements across reloads and shared views. Reject stale output
snapshots, retain state during missing observations and use provider events
when no output timestamp has ever been available. Compact activity dots belong
at the upper corner, separate from lower task/worktree markers and refresh.

This supersedes provider-only detection and manual tab-click dismissal rules
in the older terminal completion memories. See docs/terminal-completion.md.
