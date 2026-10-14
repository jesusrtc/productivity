# Agent-reported terminal status

Terminal indicators show only the agent's latest explicit report. Lab does not
infer working or finished from output, silence, a quiet deadline or provider
transcripts. Terminals without a report have no dot.

| Command | Indicator | Clears on click? |
| --- | --- | --- |
| `lab notifications working "Description"` | Steady yellow | No |
| `lab notifications attention "What needs your attention"` | Pulsing red | No |
| `lab notifications finished "What was completed"` | Blinking green | Yes |

`wip` aliases working; `input` and `review` alias attention. Hover shows the status
and optional message (maximum 500 characters). No desktop notification, pop-up,
sound or external message is sent. Reduced-motion mode keeps all dots steady.

## Agent contract

The packaged Lab launch context instructs agents to report working when starting
or resuming a task, attention before yielding for needed input/approval/review,
and finished immediately before the final response when the requested work is
complete. Report transitions rather than every tool call. An agent resuming from
attention must explicitly report working. Existing agents can load the updated
instructions with `lab context` or the context reader's drag-to-terminal action.
Outside a Lab tmux terminal, skip reporting; never choose another session by guess.

Working and attention remain until replaced by an agent report. Silence, output,
clicks, focus changes, lost connections and interrupted turns do not clear them.
A report describes the agent's state, not a test-quality judgment, and never
changes task status or completes checklist items.

## Review and shared views

An explicit click on a finished terminal tab (even the selected tab) clears its
green indicator. Enter/Space activation and direct green-dot clicks do the same.
Programmatic activation, reloads, hover and time spent selected never acknowledge
it. The next explicit report sets the next status; stale snapshots or clicks
cannot acknowledge a later report. Merged tabs use their actual selected child's
state and acknowledgement, retaining the parent's visual identity.

Workspace tabs aggregate red attention before yellow working before unread green.
A workspace green-dot click acknowledges its finished sessions, never working or
attention. Reports and acknowledgements are shared across workspace/document
views of the same terminal. Acknowledgements persist in browser storage and sync
across windows in that browser; separate browser profiles review independently.
Recency lines, task state, icons, worktree colors and terminal recovery stay separate.

## Transport and persistence

The CLI requires `TMUX` and `TMUX_PANE`. It connects to that exact socket, resolves
the calling pane's session ID/name with `display-message`, then sets the session
option `@lab_status`. It does not use whichever terminal the browser selected or
whichever socket is currently active for new launches. No server HTTP credential
is required. The report is bounded, validated and base64-encoded JSON, keeping
message punctuation, newlines and tmux format text literal in commands/listings.

The existing batched tmux listing reads the option alongside session identity.
No additional polling loop or output capture is used for status. Backend and
browser restarts preserve the live tmux report. New sessions start without a
report; browser state is keyed by socket, tmux session ID, name and creation time.
A missing observation preserves a known state; old inferred browser state is
ignored. If an agent crashes before reporting, its last report remains visible.

Provider event parsing remains available for process lifecycle/safety decisions;
it does not drive these indicators.

## Verification

CLI tests cover exact pane/socket targeting, aliases, literal messages, missing
context and failures. Native tmux/API tests use isolated disposable sessions to
verify ownership, independent sessions, listing transport and session renewal.
Frontend tests cover all three states, stale reads/clicks, reloads, shared views,
keyboard acknowledgement, hover text, compact/expanded and merged terminals,
workspace aggregation and reduced-motion styling. No fixture sends input to a
user's live terminal.
