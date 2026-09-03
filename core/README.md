# core

Core FastAPI backend for the productivity monorepo (package `core`; formerly `apps/server`, package `server`). Serves the cached global index, project/task reads and writes, markdown rendering, search, the gdiff project view, and broadcasts index-updated events over a WebSocket — defaults to **:3333**, overridable per-run.

This app absorbed `apps/backend/` (the old `lab-backend`) and `apps/gdiff/` (the project track viewer) during the backend unification. See `docs/UNIFY-BACKEND.md`.

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
back to the active workspace's `lab.toml`:

```toml
[server]
host = "127.0.0.1"
port = 3333
```

Precedence is an explicit `PORT=NNNN` Make argument, `.env`, workspace
`lab.toml`, then `3333`. The chosen port is passed through `LAB_PORT` (see
`src/core/config.py`) and
recorded in the active workspace at `.lab/state/server.port` on startup.
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
- `GET  /`                            — rich project view; use `?project=<abs path>`
- `GET  /p/{project_id}`              — redirects to `/?project=<abs path>`

Index + project/task APIs:
- `GET  /api/ping`
- `GET  /api/index`
- `GET  /api/projects[?status=...]`
- `GET  /api/projects/{id}`
- `GET  /api/projects/{id}/tasks`
- `GET  /api/projects/{id}/docs`
- `GET  /api/projects/{id}/file?path=...`
- `GET  /api/tasks[?status=...&priority=...&tag=...&label=...]`
- `GET  /api/tasks/due?days=N`
- `GET  /api/markdown?path=content/...`
- `GET  /api/search?q=...`
- `WS   /ws`

Write mutations (delegated to `lab` CLI):
- `POST   /api/projects`
- `POST   /api/tasks`
- `POST   /api/tasks/{project_id}/{task_id}/status`
- `POST   /api/tasks/{project_id}/{task_id}/update`
- `POST   /api/projects/{project_id}/prs`
- `DELETE /api/projects/{project_id}/prs/{idx}`
- `POST   /api/projects/{project_id}/artifacts`
- `DELETE /api/projects/{project_id}/artifacts/{idx}`

gdiff-absorbed project/diff routes:
- `GET    /api/diff?repo=...&type=uncommitted|branch`
- `GET    /api/commits?repo=...`
- `GET    /api/commit-diff?repo=...&sha=...`
- `GET    /api/tree?repo=...`
- `GET    /api/repos`
- `GET    /api/notebook?repo=...&path=...`
- `GET    /api/notebook-diff?repo=...&path=...&type=...`
- `GET    /api/project-info?path=...`
- `PUT    /api/project-info`
- `GET    /api/project-actions?path=...`
- `GET    /api/project-alerts?path=...`
- `GET    /api/project-artifacts?path=...`
- `GET    /api/project-onepager?path=...`
- `GET    /api/project-files?path=...`
- `GET    /api/project-file?path=...&file=...`
- `PUT    /api/project-file`
- `GET    /api/project-mtime?path=...`
- `GET    /api/project-asset?path=...&file=...`
- `GET    /api/project-comments?path=...`
- `POST   /api/project-comments`
- `DELETE /api/project-comments`
- `POST   /api/project-action-complete`
- `GET    /api/file?repo=...&path=...`
- `PUT    /api/file`
- `POST   /api/file`
- `DELETE /api/file?repo=...&path=...`
