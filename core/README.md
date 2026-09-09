# core

Core FastAPI backend for the productivity monorepo (package `core`; formerly `apps/server`, package `server`). Serves the cached global index, workspace/task reads and writes, markdown rendering, search, the gdiff workspace view, and broadcasts index-updated events over a WebSocket — defaults to **:3333**, overridable per-run.

This app absorbed `apps/backend/` (the old `lab-backend`) and `apps/gdiff/` (the workspace track viewer) during the backend unification. See `docs/UNIFY-BACKEND.md`.

## Dev

```
pip install -e .[dev]
pytest -v
```

## Run

```
make start                 # uses LAB_PORT from the client checkout's .env
make start PORT=4444       # one-run override
make stop
```

Copy the tracked template once, then edit the local setting whenever needed:

```sh
cp .env.example .env
# edit LAB_PORT=3333
make run
```

The local `.env` is ignored by Git. If `LAB_PORT` is absent there, Lab falls
back to the active vault's `lab.toml`:

```toml
[server]
host = "127.0.0.1"
port = 3333
```

Precedence is an explicit `PORT=NNNN` Make argument, `.env`, vault
`lab.toml`, then `3333`. The chosen port is passed through `LAB_PORT` (see
`src/core/config.py`) and
recorded in the active vault at `.lab/state/server.port` on startup.
Any tool/script/doc snippet that needs to call the server should resolve the
URL via `scripts/lab-url.sh` rather than hardcoding `localhost:3333`.

Local notebook automation should use `lab notebook exec`. At server startup,
Lab creates an owner-readable bearer token at
`$LAB_HOME/local-cli-token` (default `~/.lab/local-cli-token`); the CLI uses it
automatically instead of copying a browser cookie or embedding an account
password. The server accepts that token only from loopback and only for
`/api/nb` routes. Remote clients use the normal `/api/auth/login` session flow.

## Endpoints

SPA shell (gdiff-style):
- `GET  /`                            — rich workspace view; use `?workspace=<abs path>`
- `GET  /w/{workspace_id}`              — redirects to `/?workspace=<abs path>`

Index + workspace/task APIs:
- `GET  /api/ping`
- `GET  /api/index`
- `GET  /api/workspaces[?status=...]`
- `GET  /api/workspaces/{id}`
- `GET  /api/workspaces/{id}/tasks`
- `GET  /api/workspaces/{id}/docs`
- `GET  /api/workspaces/{id}/file?path=...`
- `GET  /api/tasks[?status=...&priority=...&tag=...&label=...]`
- `GET  /api/tasks/due?days=N`
- `GET  /api/markdown?path=content/...`
- `GET  /api/search?q=...`
- `WS   /ws`

Write mutations (delegated to `lab` CLI):
- `POST   /api/workspaces`
- `POST   /api/tasks`
- `POST   /api/tasks/{workspace_id}/{task_id}/status`
- `POST   /api/tasks/{workspace_id}/{task_id}/update`
- `POST   /api/workspaces/{workspace_id}/prs`
- `DELETE /api/workspaces/{workspace_id}/prs/{idx}`
- `POST   /api/workspaces/{workspace_id}/artifacts`
- `DELETE /api/workspaces/{workspace_id}/artifacts/{idx}`

gdiff-absorbed workspace/diff routes:
- `GET    /api/diff?repo=...&type=uncommitted|branch`
- `GET    /api/commits?repo=...`
- `GET    /api/commit-diff?repo=...&sha=...`
- `GET    /api/tree?repo=...`
- `GET    /api/repos`
- `GET    /api/notebook?repo=...&path=...`
- `GET    /api/notebook-diff?repo=...&path=...&type=...`
- `GET    /api/workspace-info?path=...`
- `PUT    /api/workspace-info`
- `GET    /api/workspace-actions?path=...`
- `GET    /api/workspace-alerts?path=...`
- `GET    /api/workspace-artifacts?path=...`
- `GET    /api/workspace-onepager?path=...`
- `GET    /api/workspace-files?path=...`
- `GET    /api/workspace-file?path=...&file=...`
- `PUT    /api/workspace-file`
- `GET    /api/workspace-mtime?path=...`
- `GET    /api/workspace-asset?path=...&file=...`
- `GET    /api/workspace-comments?path=...`
- `POST   /api/workspace-comments`
- `DELETE /api/workspace-comments`
- `POST   /api/workspace-action-complete`
- `GET    /api/file?repo=...&path=...`
- `PUT    /api/file`
- `POST   /api/file`
- `DELETE /api/file?repo=...&path=...`
