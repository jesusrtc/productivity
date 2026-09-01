# Terminal tabs show three requests and recover Copilot objectives

The terminal metadata API exposes the latest three cleaned direct user messages
in chronological order as `agent_session_requests`. The UI labels this history
`Requests` in the active header, console block, and hover tooltip. Keep the
scalar `agent_session_summary` equal to the latest request for compatibility.

GitHub Copilot CLI persists session identity and its title in
`~/.copilot/session-state/<id>/workspace.yaml`, conversation events in
`events.jsonl`, optional checkpoints beside them, and todos in `session.db`.
Its automatic title can remain the placeholder `Session Initialization`. If
that title was not user-authored, Lab derives the stable tab objective from the
first substantive saved `user.message`, skipping greetings, acknowledgements,
and context-free follow-ups such as `tell me more`.
