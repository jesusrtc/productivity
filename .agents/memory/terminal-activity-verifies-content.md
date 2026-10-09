# Terminal activity verifies content

On October 8, 2026 the user reported idle terminals cycling through yellow and
green, particularly SSH connections. An isolated native tmux reproduction proved
that OSC title updates advance `window_activity` without changing screen text.
Raw I/O is therefore only a gate, not evidence of work. Verify bounded joined
pane text, retaining only hashes. Cursor queries, unchanged redraws and resize
baselines cannot start a cycle. First observations establish baselines, not work.

Share a bounded locked cache across scoped/global lists. Changed panes use
batched tmux capture commands, up to 32 panes per subprocess; unchanged settled
panes need no captures. Check once after the raw timestamp's second closes so
same-second final output is not missed. Cleanup and arbitrary import discovery
must not capture contents. Failed verification remains unknown and retries.

Versioned content observations replace old raw-I/O browser signals. Retain a
quiet deadline per actual output event: cloning cached rows must not restart
the 40 seconds or revive yellow after green. New backend cache generations
establish baselines while preserving already verified unread results.
Green still clears only on explicit tab/green-dot review. Quiet does not change
task status or complete checklist items.

This supersedes the raw `window_activity` strategy in
[Terminal output quiet period and review](terminal-output-quiet-period-and-review.md).
Native tmux and Chrome regression fixtures must use disposable sessions and
synthetic terminal data, never input into the user's live sessions.
