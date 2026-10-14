# Lab framework capabilities

Lab provides documents, live notebooks, workspace/task metadata, terminals and
managed local servers. Explicit user requests and vault/workspace-owned
instructions take precedence over framework defaults.

Before working, read Lab's user guide and changelog, plus the owning vault's
root instructions and the owning workspace's root instructions, unless already
loaded. Check existing AGENTS.md (or agent.md), CLAUDE.md and
.github/copilot-instructions.md, and follow the instruction files they reference.
Read vault-wide rules first, then workspace rules, then applicable Objective,
task and working repository instructions. This includes agents starting inside
an Objective folder or linked repository/worktree; provider discovery alone may
omit the owning roots. Keep each file's scope and the user's task scope intact.

The launcher supplies absolute documentation and instruction paths for known
scopes. With Copilot, first read the LAB_AGENT_CONTEXT environment variable
(`printenv LAB_AGENT_CONTEXT`) for that launch's absolute paths. Run `lab context`
to rediscover paths in the current terminal. LAB_VAULT identifies the owning
vault; Objective/task context or workspace metadata identifies the workspace.
Read the full operating guide with `lab context user-guide` and changes with
`lab context changelog`. These commands also work in installed packages.

Use `lab --help` to discover commands. Use `lab` for managed metadata; never
hand-edit workspace.json, tasks.json or .index.json. Vaults and workspaces own
their instructions, skills and memory policy. Do not create, rewrite or symlink
agent instruction, skill or memory files merely to integrate with Lab.

## Report terminal status

Inside a Lab tmux terminal, explicitly report your state with these commands:

- `lab notifications working "Short description"` when starting or resuming work.
- `lab notifications attention "What you need from the user"` before yielding
  for input, approval, or review that requires the user's attention.
- `lab notifications finished "What was completed"` immediately before the final
  response once the requested work is finished.

These only set the terminal's dot and hover text: steady yellow for working,
pulsing red for attention, blinking green for finished. They send no pop-ups or
external messages. Report transitions, not every tool call. The command resolves
its own tmux session; never guess another terminal's name. If TMUX/TMUX_PANE are
absent, skip reporting rather than targeting another session. If reporting fails,
continue the user's work and mention the failure when relevant.

Only finished clears on an explicit tab or green-dot click. Working and attention
remain until you explicitly report a different state; resuming after input must
report working. Silence, output, interruptions and provider events never imply
finished. A status report does not change task status or check off requirements.
