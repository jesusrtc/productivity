# Sidebar task status menu

The user's October 5, 2026 request supersedes the read-only status rule in
`task-status-and-terminal-icons-are-separate.md`. Secondary-click a task or
subtask anywhere in the left Objectives column to choose Completed, Undo or
In progress. Keep ✅ for Completed and ⬜ for Undo with a red frame; use 🟡 for
In progress. The Home demo follows the same interaction.

Persist `status` as `todo`, `in_progress` or `done` in Objective manifests and
keep the legacy `done` boolean aligned. Existing manifests without `status`
remain compatible. Completed/Undo cascade to children; In progress preserves
child completion. A child status change rolls up the parent's state.

Status still belongs on the left. The separate right-side asset icon and its
drop behavior remain as described in the earlier memory. Current tabs and
linked terminals use the chosen asset icon, or the current status by default.
