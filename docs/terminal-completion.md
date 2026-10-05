# Terminal activity and completion indicators

Codex, Claude, and Copilot terminal tabs show a **steady yellow dot** from
verified work until a recorded finish, interruption, or error. Waiting for input
or approval is still unfinished work. Unknown status, partial transcript reads,
missing live conversation mappings, connection loss, switching tabs, and reloads
must not erase an already observed yellow dot. A new verified conversation has
its own state. Hover and the tab's accessible label say “Working.”

When a completed response is ready to review, a **green blinking dot** appears,
including on the active tab until acknowledged. It blinks on/off every 0.8
seconds with a slight glow. Reduced-motion preferences use a steady glowing dot.
New work never hides or acknowledges an unread completion: yellow and green
appear side by side when both apply. Hovering never acknowledges a response.

Workspace tabs aggregate their visible terminals, including terminals shared
through linked documents. If any terminal is working, the workspace shows a
steady yellow dot. Otherwise, unread completed work shows a blinking green dot.
Yellow takes precedence over green on the workspace tab without acknowledging
any unread results.

The left-edge vertical line indicates **recency only**. It stays steady and
continues to use the recent-marker color and timing settings, independently of
the activity dot.

The green dot disappears after the terminal has been continuously selected, visible, and
connected in the focused Lab window for **20 seconds**. A single click or
keyboard activation does not clear it. Switching terminals, hiding the panel,
leaving the Lab window, disconnecting, or reloading resets the viewing interval.
A new response gets its own full interval, including when it finishes in an
already open terminal. Hovering never acknowledges a response.

To dismiss it sooner, **double-click the terminal tab**. Single clicks on the tab
label, including two separate clicks, never dismiss it. When there is no unread completion,
double-click retains Rename; Rename is also available from the context menu.
Clicking **directly on the green dot** also marks the result as reviewed without
activating the terminal or switching workspaces. A workspace green dot marks all
its pending terminal results as reviewed across their shared views. Green dots
also support Enter and Space when focused.
An explicit double-click can acknowledge a previously verified response even
while the connection or live identity is temporarily unavailable.

Starting new work resets the viewing interval and prevents automatic
acknowledgement until work has stopped. The unread green dot stays visible
throughout. The acknowledgement paths are the full viewing interval, an explicit
double-click on the terminal tab, or a direct green-dot activation, shared across
views of the same terminal.

Configure the delay under **Settings → Global → Terminal appearance → Stop
blinking after viewing (seconds)**. It accepts 1–3600 seconds and is saved for
all terminal agents in this browser. Changing it restarts any pending interval.

Confirmed unread events
and acknowledgements persist in browser storage, scoped by terminal incarnation,
provider, and conversation, shared across workspace and document views. A later completion produces a
new blinking signal. An unread event survives temporary loss of provider-state information.

## Detection

Scoped terminal-list refreshes (normally every eight seconds) read the exact
conversation's recorded events. They do not infer completion from terminal text,
quiet output, CPU usage, or a process exiting. Unscoped dashboard/attach listings
do not scan transcripts.

- **Codex:** use the live TTY-to-thread mapping and the thread's indexed rollout;
  a successful `task_complete` is a completion. Main-agent reasoning, assistant
  messages, and tool calls retain working status even after the start event
  leaves the bounded transcript tail. An aborted or errored turn is
  not. A stale saved thread ID is never substituted for a missing live mapping.
- **Claude:** use the launched conversation ID and workspace transcript;
  `assistant.message.stop_reason` of `end_turn` or `stop_sequence` completes a
  response. API errors, tool calls, and `turn_duration` alone do not.
  `turn_duration` clears unfinished working state without claiming completion.
  Local CLI commands such as `/usage`, metadata, and compaction summaries do not
  start work. Recorded user interruptions clear working state.
- **Copilot:** resolve the live process on the terminal's TTY, then its latest
  foreground registration in `logs/process-<timestamp>-<pid>.log` under
  `COPILOT_HOME` (default `~/.copilot`). Reject logs older than the process and
  require its matching `session-state/<id>/inuse.<pid>.lock` ownership marker.
  Conversation switches update this mapping; the original launch ID and
  same-directory/recent transcripts are never fallback identities. Ambiguous
  processes, unavailable logs/ownership, or unsupported formats return unknown.
  Read the resolved conversation's `events.jsonl`. A successful
  `session.task_complete` is an accepted autopilot completion, including when
  the final response is delivered through the `task_complete` tool rather than
  a separate text message. Require `success: true` and an absent or `completed`
  outcome; rejected completions remain working and blocked outcomes wait for
  intervention. A successful tool execution alone is not acceptance.
  For ordinary replies, require a completed
  `assistant.message` containing text with no `toolRequests`, followed by an
  `assistant.turn_end` for that same turn. Tool batches also emit turn-end
  events, so a turn-end alone is insufficient. Errors, interruptions, and
  shutdown events do not create signals. A shutdown after a verified final
  response preserves that completion. Child-agent events are ignored.
  Resuming a session or changing its context does not start work; resume clears
  unfinished state left by the previous process with an explicit interruption
  signal, including previously observed yellow in the browser. A new request
  starts yellow again. Resume after a verified final response retains unread green.

Working is based on recorded request/turn activity, not output silence. Updates
arrive with the normal scoped refresh; a provider pause or abrupt termination
without a recorded state change cannot be distinguished from ongoing work.

The provider protocols distinguish response/turn completion from successfully
fulfilling every part of a user request. The blinking green dot means a response is ready to
review; it is not a test-success or task-quality judgment. See the
[Codex protocol](https://github.com/openai/codex/blob/main/codex-rs/protocol/src/protocol.rs),
[Claude stop reasons](https://platform.claude.com/docs/en/build-with-claude/handling-stop-reasons),
and [Copilot event schema](https://github.com/github/copilot-sdk/blob/main/nodejs/src/generated/session-events.ts).

Reads are capped at the last 2 MiB per transcript and cached by inode, size, and
mtime. Missing identities, unsupported event formats, malformed/partial records,
or files changing during a read return unknown and cannot create a new signal.
The browser retains previously verified activity through those unknown reads;
that retained conversation identity is never used to read a stale transcript.
Provider format changes should add fixtures before extending recognition.

Copilot live identity lookups are scoped to the requested TTYs and cached for
five seconds, including unresolved TTYs. Process log reads are capped at 2 MiB
and fingerprint-cached. Continuous appends preserve a verified foreground
registration; a cold read or an unread gap larger than the cap requires a
registration within the bounded tail. Partial writes, truncation, and rotation
cannot silently reuse a stale foreground mapping.

## Checks

`test_agent_activity.py` covers all three providers, intermediate tool turns,
errors, interruptions, children, malformed/partial files, cache invalidation,
bounded reads, and exact conversation lookup. `test_frontend_terminal_completion.py`
covers unread persistence, scope isolation, newer responses, uncertain state,
the exact viewing threshold, switching/visibility resets, configurable delay,
focused/visible/connected acknowledgement, persistence through identity and
connection gaps, new work during unread completion, and double-click dismissal. `test_frontend_terminal_ui.py`
checks that working dots and labels remain consistent for all three agents,
including waiting and unreachable terminals. Settings browser checks verify
the default, saving, and reopening the delay field.

Recorded, sanitized Copilot CLI 1.0.83 fixtures exercise a real tool loop,
final response, shutdown, and an idle resume after abrupt process termination.
The recordings were generated with a local deterministic provider and temporary
CLI state, without accessing existing conversations. Browser workspace checks
run for both Claude and Copilot, including yellow priority and direct green review.

A client-supplied sanitized CLI 1.0.91 autopilot fixture covers accepted
completion without a tool-free final response, including the yellow-to-green
frontend transition. Additional cases cover rejection, blocked completion,
child events, later work, and bounded reads. `test_copilot_identity.py` checks
live conversation switching, PID reuse, ownership, ambiguity, cache expiry,
partial/rotated logs, and exact-conversation route enrichment.

Browser verification uses synthetic terminal rows and a synthetic attachment
only; it must not send input to or replace the user's live agent sessions.
