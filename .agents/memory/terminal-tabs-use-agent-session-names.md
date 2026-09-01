# Terminal tabs use agent session names

Agent terminal tabs combine an explicit Lab `label` with the provider-derived
`agent_session_name` as `Manual name: Session name`. Without a manual label,
they render the provider name, then the Lab logical name, then the raw tmux
name.

Hover text and the selected-terminal header show up to three direct user
requests as `agent_session_requests`; `agent_session_summary` remains the
latest request for older clients. Prefer this provider metadata over captured
pane text, and remove image placeholders and injected instruction messages.

Provider identity is resolved without scraping pane transcript text:

- Claude Code uses Lab's known `claude_session_id` and the matching transcript
  `ai-title` / sessions index entry; the latest non-sidechain external user
  message supplies the task.
- Copilot CLI is launched with a Lab-minted `--session-id`; its name/summary is
  read from `~/.copilot/session-state/<id>/workspace.yaml`, and direct
  `user.message` requests come from `events.jsonl`. When the non-user-authored
  name stays `Session Initialization`, use the first substantive request as
  the stable objective instead.
- Codex CLI is mapped exactly from tmux pane TTY → live native PID →
  `~/.codex/logs_2.sqlite` process/thread entry → the top-level `cli` thread in
  `state_5.sqlite`; its latest projected `userMessage` comes from
  `thread_history_1.sqlite`. Read the latest three projected user messages,
  filter candidate threads by the tab cwd, and keep the lookup cached so
  normal terminal polling stays near its prior latency.

Keep `agent_session_name` dynamic and separate from the user-authored `label`;
never persist an automatically generated provider title as a manual rename.
