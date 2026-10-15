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

User requests and owning vault/workspace instructions take precedence over Lab
defaults. Opening a terminal alone does not authorize work. Lab does not create
or rewrite user instruction files as part of this bootstrap.
