# Terminal tabs use agent session names

Agent terminal tabs render identity in this order: explicit Lab `label`, the
provider-derived `agent_session_name`, the Lab logical name, then the raw tmux
name. Clearing a manual label therefore reveals the live agent session name.

Provider identity is resolved without scraping pane transcript text:

- Claude Code uses Lab's known `claude_session_id` and the matching transcript
  `ai-title` / sessions index entry.
- Copilot CLI is launched with a Lab-minted `--session-id`; its name/summary is
  read from `~/.copilot/session-state/<id>/workspace.yaml`.
- Codex CLI is mapped exactly from tmux pane TTY → live native PID →
  `~/.codex/logs_2.sqlite` process/thread entry → the top-level `cli` thread in
  `state_5.sqlite`. Filter candidate threads by the tab cwd and keep the lookup
  cached so normal terminal polling stays near its prior latency.

Keep `agent_session_name` dynamic and separate from the user-authored `label`;
never persist an automatically generated provider title as a manual rename.
