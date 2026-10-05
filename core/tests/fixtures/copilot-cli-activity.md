# Copilot CLI activity recordings

These JSONL fixtures were recorded from the installed Copilot CLI 1.0.83 on
2026-10-01. The CLI used `COPILOT_OFFLINE=true`, a local deterministic provider,
an isolated `COPILOT_HOME`, and a temporary working directory. No existing user
conversations or GitHub credentials were used.

- `copilot-cli-1.0.83-tool-response.jsonl`: a `bash` call running `sleep 2`, an
  intermediate tool turn end, a final text response, and normal shutdown.
- `copilot-cli-1.0.83-abrupt-resume.jsonl`: a request stopped by terminating the
  owned test process while its provider response was pending, followed by an
  interactive resume with no new user request and an explicit `/exit`.

Only fields relevant to activity detection are retained. Temporary paths,
system prompts, usage metrics, and tool-output metadata were removed; system
message content was replaced with test text. Event order, IDs, timestamps,
turn IDs, tool requests, and completion boundaries remain as recorded.

The [Copilot agent-loop documentation](https://github.com/github/copilot-sdk/blob/main/docs/features/agent-loop.md)
explains why a tool turn end does not finish the user response and why the
ephemeral `session.idle` event cannot be recovered from persisted JSONL logs.

## Autopilot completion (CLI 1.0.91)

`copilot-cli-1.0.91-autopilot.jsonl` is the client's sanitized reduction of a
native autopilot completion reported on 2026-10-05. The completion sequence
preserves the supplied timestamps, turn ID, ordering, empty assistant content,
tool name, and acceptance flag. IDs are replaced, the summary is test text,
and hooks, usage payloads, and unrelated conversation content are omitted.
The session start is reduced to its version marker with a synthetic timestamp.

The final assistant message requests `task_complete`; no tool-free text reply
follows. Successful tool execution alone is insufficient: the separate
`session.task_complete` event records whether completion was accepted.
Rejected and blocked completion variants in tests follow the client-reported
1.0.91 event schema (`success`, `outcome: completed | continue | blocked`).

Identity tests reproduce the supplied 1.0.91 process log lines:
`Registering foreground session: <id>` and
`Unregistering foreground session: <id>`, together with the native
`session-state/<id>/inuse.<pid>.lock` PID marker. They use isolated temporary
files and mocked process discovery, never switch or send input to live sessions.
