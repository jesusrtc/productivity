# Live notebooks in Lab

When the user wants notebook cells and execution to appear live in Lab, use
Lab's executor. It shares the notebook's kernel with the user and streams
actor, running state, timer, and outputs to the open notebook view.

```bash
lab notebook --help
lab notebook exec workspaces/<id>/notebooks/example.ipynb --code 'print(1 + 1)'
lab notebook exec workspaces/<id>/notebooks/example.ipynb --cell-id <id> --file /tmp/cell.py
```

Paths may be absolute under the selected vault, relative to the current
working directory, or vault-relative starting with workspaces/. Consecutive
cells in the same notebook share kernel state. The command waits for completion
while the UI streams progress. A configured local notebook runtime is required.

Do not substitute raw Jupyter, ipykernel, nbclient, or nbconvert execution when
live Lab execution was requested; those bypass the live-event channel. Do not
rewrite notebook JSON as a substitute for Lab's live cell APIs.

A terminal launched by Lab is pinned to its owning vault with LAB_VAULT. Check
`lab vault current` if a path is unexpected. File names, notebook structure,
and domain-specific methodology belong to the workspace and the user.
