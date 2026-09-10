# Meta is agent context; skills belong to the workspace

The sidebar Meta section shows the installed Lab launch guide and instruction
files in the selected project/worktree (AGENTS.md, CLAUDE.md, and Copilot's
instruction file). It must not render vault skill mounts, shared .agents/.claude
trees, or shared code folders. Workspace settings such as servers.json and
tasks.json stay in Files. Skills are workspace-owned files, not framework
context or automatic shared-vault links.

The guide viewer reads /api/agents/context/guide, which uses the launcher's
installed read_context source. /api/agents/context is the separate readiness
report used by settings.
