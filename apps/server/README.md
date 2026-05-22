# lab-server

Unified FastAPI backend for the productivity monorepo. Serves the cached global index, project/task reads and writes, markdown rendering, search, the gdiff project view, and broadcasts index-updated events over a WebSocket — defaults to **:3333**, overridable per-run.

This app absorbed `apps/backend/` (the old `lab-backend`) and `apps/gdiff/` (the project track viewer) during the backend unification. See `docs/UNIFY-BACKEND.md`.

## Dev

```
pip install -e .[dev]
pytest -v
```

## Run

```
make start                 # from monorepo root — serves at http://localhost:3333/
make start PORT=4444       # override the port
make stop
```

The chosen port is honored via the `LAB_PORT` env var (see `src/server/config.py`)
and recorded in `.lab-server.port` on startup. Any tool/script/doc snippet that
needs to call the server should resolve the URL via `scripts/lab-url.sh` rather
than hardcoding `localhost:3333`.

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
