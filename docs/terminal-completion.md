# Terminal completion indicators

Codex, Claude, and Copilot terminal tabs show a small blue dot for a completed
response that has not been viewed. The green left-edge line continues to mean
recently selected. Hovering shows when the response finished without clearing
the dot.

Clicking the terminal tab or its dot clears the existing dot immediately,
including while navigation or reconnecting is pending. Keyboard activation does
the same. A response finishing while its pane is visible and connected in the
focused Lab window is acknowledged automatically. Background windows, hidden
panels, and hovering do not automatically acknowledge responses. Confirmed unread events
and acknowledgements persist in browser storage, scoped by vault/workspace,
terminal incarnation, provider, and conversation. A later completion produces a
new dot. An unread event survives temporary loss of provider-state information.

## Detection

Scoped terminal-list refreshes (normally every eight seconds) read the exact
conversation's recorded events. They do not infer completion from terminal text,
quiet output, CPU usage, or a process exiting. Unscoped dashboard/attach listings
do not scan transcripts.

- **Codex:** use the live TTY-to-thread mapping and the thread's indexed rollout;
  a successful `task_complete` is a completion. An aborted or errored turn is
  not. A stale saved thread ID is never substituted for a missing live mapping.
- **Claude:** use the launched conversation ID and workspace transcript;
  `assistant.message.stop_reason` of `end_turn` or `stop_sequence` completes a
  response. API errors, tool calls, and `turn_duration` alone do not.
- **Copilot:** use the conversation's `events.jsonl`. Require a completed
  `assistant.message` containing text with no `toolRequests`, followed by an
  `assistant.turn_end` for that same turn. Tool batches also emit turn-end
  events, so a turn-end alone is insufficient. Errors, interruptions, and
  shutdown events do not create dots. Child-agent events are ignored.

The provider protocols distinguish response/turn completion from successfully
fulfilling every part of a user request. The dot means a response is ready to
review; it is not a test-success or task-quality judgment. See the
[Codex protocol](https://github.com/openai/codex/blob/main/codex-rs/protocol/src/protocol.rs),
[Claude stop reasons](https://platform.claude.com/docs/en/build-with-claude/handling-stop-reasons),
and [Copilot event schema](https://github.com/github/copilot-sdk/blob/main/nodejs/src/generated/session-events.ts).

Reads are capped at the last 2 MiB per transcript and cached by inode, size, and
mtime. Missing identities, unsupported event formats, malformed/partial records,
or files changing during a read return unknown and cannot create a new dot.
Provider format changes should add fixtures before extending recognition.

## Checks

`test_agent_activity.py` covers all three providers, intermediate tool turns,
errors, interruptions, children, malformed/partial files, cache invalidation,
bounded reads, and exact conversation lookup. `test_frontend_terminal_completion.py`
covers unread persistence, scope isolation, newer responses, uncertain state,
immediate click acknowledgement, and focused/visible/connected automatic acknowledgement.

Browser verification uses synthetic terminal rows and a synthetic attachment
only; it must not send input to or replace the user's live agent sessions.
