# META includes scoped skill folders

The October 16, 2026 request supersedes the earlier META-is-not-skills rule.
Show existing skill folders for the owning vault, workspace and current
Objective, plus a separate selected folder/worktree when applicable. Cover
skills/, content/skills/, .agents/skills/, .claude/skills/, .codex/skills/,
.github/skills/, .copilot/skills/ and legacy Claude .claude/commands/.

Only present directories get rows. Include every nested folder/file, including
hidden and empty folders, without a whole-repository scan or Files dotfile
dependency. Retain expansion during refresh, scope file actions to their owning
root, follow existing skill symlinks and stop ancestor cycles. Discovery is
read-only and does not install, link, load or run skills. Keep API/CLI access.
