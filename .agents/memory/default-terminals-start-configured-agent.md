# Default terminals start the configured agent

The user wants workspace and Objective default terminals to open the selected
agent, including Codex or Copilot, with Lab context supplied at initialization.
Fixed workflow/Objective mains and automatically requested task terminals use
the normal agent launch path with workspace/global default resolution and
`lab agents run`; do not start a bare shell for these default entries. Explicit
**+ New → Terminal** still requests a shell. Keep existing running terminals
and their startup context unchanged.
