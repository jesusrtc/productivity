# Lab framework capabilities

## Startup and context recovery

At the start of every agent session, including a resumed conversation, and
after context compaction, run `lab context llm` before other tools. It always
prints this guide, the full Lab user guide, new changelog differences, and the applicable
owning instruction paths. Read its complete output, retrieving any truncated
remainder before working. When reading that output, the bootstrap is already
complete; do not rerun it merely because these instructions mention it.

The command marks the calling Lab tmux terminal as LLM-controlled and records
the context version after successful output. No separate `lab terminal llm`
step is needed. Outside tmux it prints the same context without storing markers.

## Required at every turn

At the start of each subsequent user turn, including short requests, greetings,
and work resumed after input, run `lab context update` before other tools.
Read and follow any context it prints before continuing. Empty output means your
tmux session already has the current version; do not reread it unnecessarily.
`lab context version` prints only the current numeric version. The launcher
preserves the previous version for changelog diffs; llm/update record the new
version only after printing the context and storing its changelog snapshot.
These commands do not update code,
restart anything, or edit workspace instructions.

Inside a Lab terminal, status reporting is required even for a ten-second wait
or a one-line answer. After checking context, run
`lab notifications working "Short description"` before doing the requested work.
Immediately before your final reply, run
`lab notifications finished "What was completed"`, or
`lab notifications attention "What you need from the user"` if input, approval,
or review is needed to continue. Execute these commands; mentioning them in prose
does not report a status. The CLI does not infer these transitions for you.
Treat the final status report as a prerequisite to replying: confirm that the
command succeeded. If socket access is blocked, use the normal permission retry
described below; if that also fails, disclose the reporting failure in your reply.

Lab provides documents, live notebooks, workspace/task metadata, terminals and
managed local servers. Explicit user requests and vault/workspace-owned
instructions take precedence over framework defaults.

Before working, read the combined Lab context (this guide and the user guide),
any new changelog differences returned by llm/update, plus the owning vault's
root instructions and the owning workspace's root instructions, unless already
loaded. Check existing AGENTS.md (or agent.md), CLAUDE.md and
.github/copilot-instructions.md, and follow the instruction files they reference.
Read vault-wide rules first, then workspace rules, then applicable Objective,
task and working repository instructions. This includes agents starting inside
an Objective folder or linked repository/worktree; provider discovery alone may
omit the owning roots. Keep each file's scope and the user's task scope intact.

The launcher reinforces the startup command and supplies absolute documentation
and instruction paths for known scopes. `lab context llm` resolves these paths
directly for every provider, including Copilot; no separate environment read is
needed. Run `lab context` to rediscover paths in the current terminal.
LAB_VAULT identifies the owning
vault; Objective/task context or workspace metadata identifies the workspace.
META shows the same combined instructions and user guide as **Lab context**.
The full changelog is available on demand with `lab context changelog`.
If a terminal has no previous snapshot, the first read establishes its baseline
instead of guessing a diff. These commands also work in installed packages.

Use `lab --help` to discover commands. Use `lab` for managed metadata; never
hand-edit workspace.json, tasks.json or .index.json. Vaults and workspaces own
their instructions, skills and memory policy. Client reloads automatically
refresh Lab's marked AGENTS.md section in the loaded vault/workspace/Objective
and an existing framework checkout instruction file. The installed template
owns this section for every client. `lab agents refresh` exposes the same scoped
writer manually. Keep custom rules outside that section, and change shared Lab
rules in the packaged template instead of hand-editing a client's AGENTS.md.
Otherwise do not create, rewrite or symlink agent instruction,
skill or memory files merely to integrate with Lab.

## Delegating to subagents

When the user asks for subagents or delegation, launch each delegated agent
through `lab agents spawn --name "Short task" --prompt-file /absolute/task.txt`
(or `--prompt "Task"`). Each runs in its own tmux session and appears beneath
your calling terminal in Lab. This works for Copilot, Codex and Claude; the child
uses your provider unless you pass `--agent copilot|codex|claude`.
Do not substitute invisible provider-internal workers or hand-create tmux sessions
when the user requested visible Lab subagents. Do not delegate without authorization.

Write a bounded assignment with its scope, constraints and expected result.
The child inherits your vault, workspace and launch folder, reads the same Lab
context and owning instructions, and reports its own status. It starts a fresh
conversation; it does not automatically receive your conversation or unsaved work.
Coordinate shared-file edits. Use `lab agents children` to inspect reports and
`lab agents read CHILD_ID --lines 200` for bounded output; these do not select
or review the child. Inspect results before reporting the overall task finished.

The spawn command prints a launch request UUID before sending the request. If
it times out, retry the same task with `--request-id UUID`; never blindly launch
another copy. Stopped children are not automatically relaunched on reload.
Use `lab agents spawn --help` for the complete command interface.

## Record requests, assignments and changed files

Before changing files for a new user request, run
`lab agents work start --title "Request summary"` (add `--request-file` for the
request and `--context-file` for decisions/constraints). These are agent work
assignments, completely separate from Objective tasks and their checklists.
For a delegated assignment, resume the `--id` supplied in its launch prompt.
Use `--parent ASSIGNMENT_ID` for a sub-assignment. Track each request separately.

After edits, record the exact files you created/changed with
`lab agents files record --operation modified /absolute/file ...` or `created`.
Use `deleted` for removed files and `renamed --previous-path OLD NEW` for renames.
Record generated documents, code, notebooks, images and other artifacts too.
Do not claim files another agent changed, a whole Git dirty set, or files you only
read. `lab agents files list` audits your record. Before the final status/reply,
run `lab agents work finish --summary "Result and validation"`; status dots still
require `lab notifications finished/attention` independently. Update the file
record again if further edits are needed. Report tracking failures explicitly.

Before delegating, give the child its bounded assignment, relevant user context,
decisions, constraints, permitted file scope and expected results. Use
`lab agents spawn --context-file /absolute/brief.txt --include-file /absolute/reference.md`
alongside its `--name` and `--prompt-file`. Only include relevant, authorized file
content; do not copy unrelated conversations, credentials or every file in a repo.
Lab also injects the parent request title, ID and recorded context, and links the
child's assignment. The raw parent conversation is not copied automatically.
Children follow the same rules if asked to delegate further. Inspect the child’s
reported files and results before marking the parent request complete.

Double-clicking an agent terminal shows its reported files grouped by request
and delegated assignment. This is an attribution record, not a full filesystem
audit or an Objective task status. Earlier unrecorded edits cannot be attributed
retroactively without evidence.

## Report terminal status

The startup `lab context llm` command marks the terminal LLM-controlled, including
when started manually from a shell. Lab launches already set this marker.
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
external messages. Report transitions and meaningful checkpoints, not every tool call.
During long work, update `lab notifications working` at least every 20 minutes:
say what you completed, what you are doing now and what comes next. If waiting
for a long process, identify it and explain the wait. A timer or process heartbeat
must never invent a progress report. Lab alerts the user after 30 minutes without
a report; only a real report resolves it. Copilot launches include a checkpoint
hook after tools and a final-status reminder; a blocking tool can delay delivery.
The command resolves
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
