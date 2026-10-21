# Lab framework capabilities

At the start of every agent session, including a resumed conversation, and after
context compaction, run `lab context llm` before other tools and follow the
instructions it returns before working. Read its complete output; increase your
tool's output limit or retrieve any truncated remainder before proceeding.

This command loads the current Lab agent instructions and full user guide,
includes only changelog changes since this terminal's last acknowledged version,
and identifies applicable owning instruction files. It also marks
the calling Lab terminal as LLM-controlled. An unchanged version in tmux does
not mean this conversation has read those instructions. On subsequent turns,
run `lab context update` before other tools and follow any changed context.

## Required terminal status on every turn

When explicitly asked to delegate, use `lab agents spawn --name "Task" --prompt-file
/absolute/task.txt` for a separate tmux child visible beneath this terminal.
Copilot, Codex and Claude share this command. Do not substitute invisible workers.
Read `lab context llm` for parent/child status, result inspection and retry rules.

Inside a Lab tmux terminal, after reading context, execute
`lab notifications working "Short description"` before work. This includes
short answers, acknowledgements, approvals and resumed work. Before every final
reply, execute `lab notifications finished "What was completed"`, or
`lab notifications attention "What is needed"` when yielding for required input,
approval or review. A successful final status report is a prerequisite to replying;
describing status in prose does not report it.

During long work, report a meaningful progress checkpoint with
`lab notifications working` at least every 20 minutes, including what changed,
your current step and what comes next (or which long process you are waiting for).
Lab alerts the user after 30 minutes without a report. Automatic activity does
not reset this clock; only an explicit agent report does.

If a sandbox blocks the tmux socket, retry the same command with the tool's
normal permission mechanism. If reporting still fails, state that failure in
the final reply. Check `TMUX`/`TMUX_PANE` before deciding you are outside Lab;
never assume status reporting does not apply.

User requests and owning vault/workspace instructions take precedence over Lab
defaults. Opening a terminal alone does not authorize work. Lab does not create
or rewrite user instruction files as part of this bootstrap.
