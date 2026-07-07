# Lab server needs out-of-sandbox start for external active workspaces

When the active Lab workspace is outside this repo, the core server writes
runtime logs/state under that workspace's `.lab/state`. Starting it from the
Codex sandbox can fail at FastAPI startup with `PermissionError` on
`.../.lab/state/logs/backend.log`. Start it outside the sandbox, preferably in a
dedicated tmux socket such as `tmux -L lab-core-server`, so the supervisor keeps
running after Codex command cleanup.
