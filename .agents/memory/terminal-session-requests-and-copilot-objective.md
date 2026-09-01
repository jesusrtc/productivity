# Terminal sessions prefer real recaps over request history

The terminal metadata API exposes every cleaned direct user message since the
most recent `/clear` as chronological `agent_session_requests`. When a current
AI recap exists, expose it separately as `agent_session_objective`; keep
`agent_session_summary` equal to the objective or latest request for older
clients.

GitHub Copilot CLI persists session identity and its title in
`~/.copilot/session-state/<id>/workspace.yaml`, conversation events in
`events.jsonl`, optional AI checkpoints in `~/.copilot/session-store.db`, and
todos in the per-session `session.db`. Its automatic name can remain the
placeholder `Session Initialization` with `summary_count: 0`; that means no
objective is available, so use all saved `user.message` events instead. If a
checkpoint exists, its title/overview is the preferred two-line objective.

Claude `system/away_summary` events are usable recaps only until a later user
turn. Codex has a generated thread name but no rolling objective in its local
SQLite projection, so trust that name as an objective only for a one-request
conversation; follow-ups switch the context view to request history.
