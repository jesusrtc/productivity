from __future__ import annotations


NOTEBOOK_SECTION_MARKER = "## Lab notebooks (live execution)"

NOTEBOOK_AGENT_SECTION = f"""{NOTEBOOK_SECTION_MARKER}

When asked to add, edit, run, or rerun a code cell in a repository `.ipynb`,
use Lab's notebook executor so people can see the agent, running state, elapsed
time, and output while the kernel is still busy:

```bash
lab notebook exec projects/<project-id>/<path>.ipynb --code 'print("hello")'
lab notebook exec projects/<project-id>/<path>.ipynb --cell-id <id> --file /tmp/cell.py
```

The command waits for the final result in the terminal, but the open Jupyter
view updates immediately and streams kernel output as it arrives. The notebook
path owns the kernel session, so consecutive calls share variables.

Do **not** hand-edit notebook JSON and then launch `jupyter`, `ipykernel`,
`nbclient`, or `nbconvert` to execute it. Those paths bypass Lab's live-event
channel and the UI can only discover the final file after execution finishes.
"""
