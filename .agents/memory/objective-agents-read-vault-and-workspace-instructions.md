# Objective agents read vault and workspace instructions

The user requires every agent working on an Objective or task to know both the
owning vault's root agent instructions and the owning workspace's root agent
instructions. The packaged Lab overview and Objectives context explicitly
require reading both levels before working, unless already loaded, as well as
applicable Objective/task and working-repository instructions.

LAB_VAULT identifies the owning vault. Resolve the owning workspace from the
Objective/task context or workspace metadata; an agent's startup folder or linked
worktree may sit outside it, so provider ancestor discovery is insufficient.
Read existing AGENTS.md (or agent.md), CLAUDE.md, applicable Copilot instructions
and referenced instruction files with their scopes preserved. This is launch
guidance, not permission to expand task scope or generate/symlink user rules.
