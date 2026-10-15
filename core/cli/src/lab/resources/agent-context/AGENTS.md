# Lab framework capabilities

## Required at every turn

At the start of every user turn, including short requests, greetings, and work
resumed after input or compaction, run `lab context update` before other tools.
Read and follow any context it prints before continuing. Empty output means your
tmux session already has the current version; do not reread it unnecessarily.
`lab context version` prints only the current numeric version. The launcher
records the version it supplied in the calling tmux session; update records a
new version only after printing its context. These commands do not update code,
restart anything, or edit workspace instructions.

Inside a Lab terminal, status reporting is required even for a ten-second wait
or a one-line answer. After checking context, run
`lab notifications working "Short description"` before doing the requested work.
Immediately before your final reply, run
`lab notifications finished "What was completed"`, or
`lab notifications attention "What you need from the user"` if input, approval,
or review is needed to continue. Execute these commands; mentioning them in prose
does not report a status. The CLI does not infer these transitions for you.

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

At the start of an agent session inside a Lab tmux terminal, run
`lab terminal llm` to mark it LLM-controlled, including when started manually
from a shell. This command is idempotent; Lab launches already set the marker.
It does not report working or finished. `lab terminal llm --off` restores
ordinary shell behavior when the terminal is no longer used for an agent.

Inside a Lab tmux terminal, explicitly report your state with these commands:

- `lab notifications working "Short description"` when starting or resuming work.
- `lab notifications attention "What you need from the user"` before yielding
  for input, approval, or review that requires the user's attention.
- `lab notifications finished "What was completed"` immediately before the final
  response once the requested work is finished.

These only set the terminal's dot and hover text: steady yellow for working,
pulsing red for attention, blinking green for finished. They send no pop-ups or
external messages. Report transitions, not every tool call. The command resolves
its own tmux session; never guess another terminal's name. A launch identifying
your Lab terminal above confirms that reporting applies. Otherwise check whether
TMUX/TMUX_PANE exist before skipping reporting; do not assume they are absent.
Outside a Lab tmux terminal, skip reporting. If a sandbox blocks the tmux socket,
use the tool's normal approval mechanism for the same command. If reporting still
fails, continue the user's work and mention the failure when relevant.

Only finished clears on an explicit tab or green-dot click. Submitting a message
in an LLM-controlled terminal immediately shows yellow; a response to red shows
`Working - responded {response}` until your next report. Still report working
with the actual task when resuming. Other working/attention transitions require
an explicit report. Silence, output, interruptions and provider events never imply
finished. A status report does not change task status or check off requirements.
