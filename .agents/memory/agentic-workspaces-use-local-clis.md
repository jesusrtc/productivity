# Agentic workspaces use installed CLIs

- One coordinator chat per workspace organizes missions and task executors. Up to five executors run alongside that coordinator.
- Use installed Codex CLI, Copilot CLI and Claude Code accounts; no direct model API client or orchestration cloud service.
- Keep exact assignments, run history, inputs, supporting notebooks, source links and outputs inspectable beside the chat. Execute notebooks with `lab notebook exec`.
- Preserve user preview approvals, local schedules, blocked/review reminders and workspace-owned instructions/skills/memory. Provider changes retain Lab's shared state.
- See `docs/AGENTIC-WORKSPACES.md` for the operational contract and opt-in real-CLI verification scripts.
