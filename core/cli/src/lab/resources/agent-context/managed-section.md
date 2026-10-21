<!-- lab:managed-context:start -->
## Lab managed

Important: On startup, run `lab context llm`, read its full output and follow its instructions before working.

On every subsequent user turn, run `lab context update` first. Inside a Lab tmux
terminal, execute `lab notifications working "Short description"` before work,
including short answers and approval follow-ups. Before every final reply, execute
`lab notifications finished "What was completed"`, or
`lab notifications attention "What is needed"` when input/approval/review is needed.
A successful final status report is required before replying. If the sandbox blocks
tmux, retry the same command with the tool's normal permission mechanism; if it
still fails, report the failure. Do not silently omit these commands.

When the user requests subagents, use `lab agents spawn --name "Task" --prompt-file
/absolute/task.txt` so each Copilot, Codex or Claude agent runs in a separate tmux
terminal nested beneath its calling parent in Lab. Read the delegation and retry
rules in `lab context llm`; inspect child results before reporting overall completion.

Record each request with `lab agents work start --title "Request"`, the exact files
you change with `lab agents files record PATH ...`, and its result with
`lab agents work finish --summary "Result"`. These are agent assignments, not
Objective tasks. Parents pass relevant context with spawn's `--context-file` and
`--include-file`; children resume their supplied assignment ID and record their
own file changes. Read the full rules in `lab context llm`.
<!-- lab:managed-context:end -->
