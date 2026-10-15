# One command bootstraps full LLM context

The user approved `lab context llm` as the single Lab entry point for an agent's
AGENTS.md: run it at every session start (including resumed conversations) and
after compaction, and follow the returned instructions. It always prints the
agent guide, full canonical user guide/changelog and scoped instruction paths,
even when the tmux version is current. It also marks that exact terminal as
LLM-controlled, replacing the separate startup `lab terminal llm` step.

Subsequent turns run `lab context update`: silent unchanged, otherwise the same
consolidated context. Only successful output acknowledges the context version.
Launchers inject a short bootstrap and leave full context unread until the agent
runs it. Preserve existing provider/user instructions and do not generate or edit
workspace AGENTS files. Full reads must recover any tool-output truncation.

This supersedes the launcher-acknowledged overview-only behavior in
agent-context-refreshes-per-terminal.md. Working/attention/finished reports and
immediate yellow feedback on user submissions keep their existing behavior.
