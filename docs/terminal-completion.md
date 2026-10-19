# Agent-reported terminal status

Terminal indicators show the agent's latest explicit report, with immediate
yellow feedback when the user submits a message to an LLM terminal. Lab does not
infer working or finished from output, silence, a quiet deadline or provider
transcripts. Terminals without a report or submitted LLM message have no dot.

| Command | Indicator | Clears on click? |
| --- | --- | --- |
| `lab notifications working "Description"` | Steady yellow | No |
| `lab notifications attention "What needs your attention"` | Pulsing red | No |
| `lab notifications finished "What was completed"` | Blinking green | Yes |

`wip` aliases working; `input` and `review` alias attention. Hover shows the status
and optional message (maximum 500 characters). No desktop notification, pop-up,
sound or external message is sent. Reduced-motion mode keeps all dots steady.

## Agent contract

The packaged Lab launch bootstrap identifies the calling terminal/pane and requires
`lab context llm` at startup and after compaction. This always prints the agent
guide, full user guide, per-terminal changelog differences and owning instruction paths, and marks the
terminal LLM-controlled without a separate `lab terminal llm` step.
On subsequent turns `lab context update` checks the current
numeric content version against that session's `@lab_context_version`: unchanged
is silent; changed or missing prints the same consolidated context and records it
after successful output and snapshot storage. New launches preserve the last
acknowledged version for diffs; the startup llm read remains mandatory. Versions cover
the bootstrap and all packaged topics,
the instruction-path template and canonical user guide/changelog, compare by
equality, and do not depend on timestamps. Reading `lab context` alone does not
acknowledge an update. Outside tmux, llm/update always print and store nothing.

Agents must then report working before the requested work on every user turn,
including greetings and short waits, attention before yielding for needed input/approval/review,
and finished immediately before the final response when the requested work is
complete. Report transitions rather than every tool call. An agent resuming from
attention must explicitly report working. Existing agents can load the updated
instructions once with `lab context llm` or the context reader's drag-to-terminal action;
older loaded instructions cannot trigger a check they do not yet describe.
Outside a Lab tmux terminal, skip reporting; never choose another session by guess.

The shared managed template, compact provider startup instructions and
generated Lab managed sections state these commands directly. Client reloads
refresh the applicable managed sections from the installed template; shared
reporting rules must not be added to custom client-owned instructions. Short answers,
acknowledgements and approval follow-ups have the same requirement. Before a
final reply, confirm that the finished/attention command succeeded. If the sandbox
blocks the tmux socket, retry the same command with the tool's normal permission
mechanism. If that retry fails, disclose the reporting failure in the final reply.
An LLM-controlled marker or automatic yellow submission indicator does not count
as the agent's explicit report.

Working and attention remain until replaced by an agent report or submitted LLM
input (yellow). Silence, output,
clicks, focus changes, lost connections and interrupted turns do not clear them.
A report describes the agent's state, not a test-quality judgment, and never
changes task status or completes checklist items.

## LLM control and submitted input

`lab agents run` marks the exact calling tmux session with `@lab_llm` before
executing the provider, restoring the previous value if execution fails. Agents
started manually should run `lab context llm` for the full bootstrap (or
`lab terminal llm` for marker-only control); the server also recognizes local
Codex, Claude and Copilot processes under that pane's process tree during normal
refresh. It checks executable/script identity, never prompt text. A detected
provider is retained with the session marker; no workspace metadata is rewritten.
Existing Lab agent tabs are treated as controlled. Explicit `lab terminal llm
--off` overrides detection and old launch identity until re-enabled. The marker
lasts for the tmux session and is exposed in hover/diagnostics, without another dot.

Only input actually sent through an open terminal connection is observed. Enter
submits; bracketed paste, typing, mouse reports, terminal replies and focus alone
do not. An LLM submission immediately shows **Working - submitted {message}**;
when answering red it shows **Working - responded {response}**. Simple editing
is tracked for the bounded hover preview. Unknown edits/history use generic text
instead of guessing. Local `/clear` and `/new` commands do not start work.

This temporary state is stored separately from the raw agent report and shared
across windows in the same browser profile. Stale/missing report polls cannot
restore red or green; the next newer agent report replaces the temporary state.
Separate browser profiles only share the tmux report. Unsent drafts stay in memory.
`lab ui terminal-status` exposes `llm_controlled`, `pending` and the
`user-submission` reason alongside the authoritative report. Submitting input
does not acknowledge a finished report, and stale green clicks cannot clear yellow.

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

Floating cards at the top right show one message per terminal across workspaces
and vaults, with red input requests first. Red messages remain until status changes, including
immediate yellow after a submitted reply. Clicking red navigates to the exact
owning workspace, Objective and terminal without clearing it. Green messages
remain until reviewed by click or replaced by a newer terminal status, with no
expiry timer. Reloading preserves unreviewed messages.
Clicking green opens the terminal and acknowledges only that displayed report,
clearing its green dot and message across shared views. A failed navigation or
an outdated click cannot consume a newer report. Clicking either color reveals
and scrolls to its destination tab, then pulses the background and outline three
times. The pulse survives tab rerenders without extending its 2.4-second duration;
another click restarts it. Reduced motion uses a steady highlight instead.
Collapsed groups and the selected Objective's task filter open only when needed
to show the destination. Workspace, Home and Assistant dots retain
red/yellow/green precedence.
Cards overlay the interface without resizing the console, including when the
terminal panel is closed. They are in-app elements, not desktop notifications.

Notification and ordinary tab navigation share task selection: explicit or
inherited task ownership comes first, then a unique assignment of the linked
asset when no task is bound. Open the asset within that task context, or the task
details without an asset, and attach the exact session rather than its primary.
Linked folders keep the task's assets visible. An asset in a different Objective
does not override explicit task ownership; shared assets do not pick an arbitrary
task.

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

Launch-context tests verify provider handoff, retained changelog baselines, repeated
full bootstrap, failed-launch rollback, silent unchanged checks, changed context,
failed output and independent
sessions. A real provider smoke test must also confirm that the agent itself
executes the check and status commands for an ordinary request; command and UI
fixtures alone cannot establish that the model follows the instructions.
