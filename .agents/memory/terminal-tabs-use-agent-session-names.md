# Terminal tabs avoid stale provider titles

An explicit Lab `label` is the complete tab name and always wins. Without one,
an agent tab may use the provider-derived `agent_session_name` while the
conversation has zero or one direct request. Once two or more requests exist,
fall back to the Lab logical name: Codex/Claude/Copilot titles are generally
generated once and can become misleading after a new task or follow-up.

The generated provider title is identity metadata, not proof of the current
objective. Never persist it as a manual rename, and do not put it above the
request history in the hover card.

Provider identity is resolved without scraping pane transcript text:

- Claude Code uses Lab's known `claude_session_id` and the matching transcript
  `ai-title` / sessions index entry.
- Copilot CLI is launched with a Lab-minted `--session-id`; its name/summary is
  read from `~/.copilot/session-state/<id>/workspace.yaml`. Ignore a
  non-user-authored `Session Initialization` placeholder rather than deriving
  another stale title from the first request.
- Codex CLI is mapped exactly from tmux pane TTY → live native PID →
  `~/.codex/logs_2.sqlite` process/thread entry → the top-level `cli` thread in
  `state_5.sqlite`; projected user messages come from
  `thread_history_1.sqlite`. Filter candidate threads by tab cwd and keep the
  lookup cached so normal terminal polling stays near its prior latency.

After `/clear`, discard the old provider title as well as the old requests.
