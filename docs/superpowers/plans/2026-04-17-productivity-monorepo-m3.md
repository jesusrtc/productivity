# Productivity Monorepo — Plan 3 (M3: Frontend + write routes + Plan-2 cleanup)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a working single-page web UI on `http://localhost:3333/` with dashboard, project view, timeline (Gantt + list), and markdown viewer — all live-updating via WebSocket. Add the POST routes the frontend needs for mouse-driven edits. Fold Plan-2 tech debt into opening commits.

**Architecture:** Vanilla HTML + ES modules served by the same FastAPI backend. Frontend fetches `/api/*` JSON, renders DOM, subscribes to `/ws` for invalidations. Writes go through new POST routes that proxy to `lab` via `subprocess.run` (keeps CLI as the only write-validation path). Route reuses lab's `_validate_id` and shared helpers. No build step, no framework dependency.

**Tech Stack:** FastAPI + Jinja2 templates (for the index.html shell), ES modules (no transpiler), `marked` via CDN for client-side markdown fallback, `chart.js` deferred (Plan 4 if Gantt needs it). Re-uses Plans 1 and 2 infrastructure unchanged.

**Out of scope for Plan 3 (deferred):**
- Worktree commands (`lab project add`/`remove`), MP prefix config — Plan 4.
- `lab search` + `/api/search` — Plan 5.
- `lab pr add`, `lab artifact add`, `lab note` — Plan 5.
- Migration agent + `lab migrate` — Plan 6.
- Tool apps migration (`apps/darwin-runner` etc.) — Plan 7.
- Diff rendering + gdiff merge — Plan 8.
- Seed data / sample projects — Plan 9.
- Mobile responsive layout. Keep it desktop-first.
- Authentication. Binds to 127.0.0.1 only.

**By the end of Plan 3, this all works:**

```
http://localhost:3333/
  /                     → dashboard (project grid + due-this-week strip)
  /p/<id>               → project view (tasks, docs, artifacts tabs)
  /timeline             → Gantt + List sub-views (tab-switched)
  /md?path=...          → markdown viewer
  /api/*                → (existing Plan 2 routes)
  POST /api/projects    → create new project (proxies to `lab project new`)
  POST /api/tasks       → create new task
  POST /api/tasks/{project}/{id}/status → transition task status
  POST /api/tasks/{project}/{id}/update → set task field
  WS /ws                → live `index-updated` broadcasts (existing)
```

And the user can fully drive the system from the browser: create projects, add/close tasks, flip statuses, view docs rendered as markdown, watch the dashboard live-update as changes happen.

---

## File Structure

### New files

```
apps/backend/src/backend/
├── routes/
│   └── mutation.py              # POST routes that shell out to `lab`
├── templates/
│   ├── index.html               # SPA shell
│   └── base.html                # (optional) layout if needed
└── static/
    ├── css/
    │   └── app.css              # base theme, grid, typography
    └── js/
        ├── app.js               # router + WS subscription
        ├── api.js               # fetch helpers (GET, POST) + WS client
        ├── views/
        │   ├── dashboard.js     # home view
        │   ├── project.js       # project detail view
        │   ├── timeline.js      # gantt + list sub-views
        │   └── markdown.js      # md viewer
        └── lib/
            └── dom.js           # tiny h() helper + toggle/render utilities

apps/backend/tests/
├── test_mutation_routes.py       # POST route tests
├── test_static.py                # verifies /, /p/<id>, /timeline serve index.html
└── test_cors.py                  # /api/index reachable cross-origin

Makefile updates for `make start` to print the URL.
```

### Modified files (Plan 2 tech-debt cleanup, bundled in Task 1)

```
apps/backend/src/backend/state.py          # add `IndexCache.root` property; prune broken WS sockets inline
apps/backend/src/backend/main.py           # add CORSMiddleware; mount static + templates; catch-all for SPA routes
apps/backend/src/backend/config.py         # default LAB_HOST to "127.0.0.1"
apps/backend/src/backend/routes/project.py # use IndexCache.root (not _root); dedupe _validate_project_id → lab.model
apps/backend/src/backend/routes/markdown.py # re-add "toc" extension; use IndexCache.root
apps/backend/src/backend/routes/task.py    # delete dead `days < 1` branch
apps/backend/tests/conftest.py             # rename _RebuildingClient → MaterializedClient; drop unused import
apps/lab/src/lab/commands/task.py          # add else branch to set_field
Makefile                                    # chain test targets with &&; print URL in start
```

### Responsibilities per file

- `routes/mutation.py` — POST endpoints. Each validates its body (Pydantic models), shells out to `lab`, surfaces non-zero exit as HTTP 400 with stderr, returns the updated row.
- `templates/index.html` — the one-page shell. Loads `/static/js/app.js` as a module. Contains a `<main id="view">` slot the router populates.
- `static/js/app.js` — hash-based router (`#/`, `#/p/<id>`, `#/timeline`, `#/md?path=...`). Subscribes to `/ws`; on `index-updated`, re-fetches the current view.
- `static/js/api.js` — `get(path)`, `post(path, body)`, `subscribe(onEvent)` for the WS.
- `static/js/views/*.js` — each exports a `render(el, params)` function. Called by the router.
- `static/js/lib/dom.js` — `h(tag, attrs, ...children)` and `clear(el)` helpers. No framework.

---

## Task 1: Plan-2 tech-debt cleanup

**Files:**
- Modify: `apps/backend/src/backend/state.py`
- Modify: `apps/backend/src/backend/config.py`
- Modify: `apps/backend/src/backend/routes/project.py`
- Modify: `apps/backend/src/backend/routes/markdown.py`
- Modify: `apps/backend/src/backend/routes/task.py`
- Modify: `apps/backend/tests/conftest.py`
- Modify: `apps/lab/src/lab/commands/task.py`
- Modify: `Makefile`

Bundle of 8 cleanups flagged by Plan 2's final review. Each is surgical.

- [ ] **Step 1: Add `root` property to `IndexCache`**

Edit `apps/backend/src/backend/state.py`. In the `IndexCache` class, add after `__init__`:

```python
    @property
    def root(self) -> Path:
        return self._root
```

- [ ] **Step 2: Prune broken sockets in `WsBroadcaster.publish`**

Replace the `publish` method in `state.py` with:

```python
    async def publish(self, event: IndexUpdatedEvent) -> None:
        async with self._lock:
            clients = list(self._clients)
        broken: list = []
        for ws in clients:
            try:
                await ws.send_json(event.to_json())
            except Exception:
                broken.append(ws)
        if broken:
            async with self._lock:
                for ws in broken:
                    if ws in self._clients:
                        self._clients.remove(ws)
```

- [ ] **Step 3: Default `LAB_HOST` to `127.0.0.1`**

Edit `apps/backend/src/backend/config.py`. Change:

```python
def host() -> str:
    return os.environ.get("LAB_HOST", "127.0.0.1")
```

- [ ] **Step 4: Dedupe `_validate_project_id` in backend**

Edit `apps/backend/src/backend/routes/project.py`. Replace the local regex + validator with:

```python
from lab.model import ModelError, _validate_id


def _validate_project_id(project_id: str) -> None:
    try:
        _validate_id(project_id)
    except ModelError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
```

Delete the now-unused `_ID_RE` constant. Remove `import re` if it's no longer used.

Also: replace every `request.app.state.index_cache._root` with `request.app.state.index_cache.root` (uses the new public property from Step 1).

- [ ] **Step 5: Update `markdown.py`**

Edit `apps/backend/src/backend/routes/markdown.py`:
- Re-add `"toc"` to the extensions list.
- Replace `request.app.state.index_cache._root` with `.root`.

Final extensions line:
```python
_RENDERER = _md.Markdown(
    extensions=["fenced_code", "codehilite", "tables", "toc", "nl2br", "sane_lists"],
    extension_configs={"codehilite": {"css_class": "highlight", "guess_lang": False}},
)
```

Because `toc` adds `id` attributes to headings, update `apps/backend/tests/test_markdown_route.py`:
- `"<h1>Hello</h1>" in body["html"]` → `"Hello</h1>" in body["html"]` (looser match)
- `"<h1>Body</h1>" in body["html"]` → `"Body</h1>" in body["html"]`

- [ ] **Step 6: Delete dead branch in `task.py` (backend)**

Edit `apps/backend/src/backend/routes/task.py`. In `list_tasks_due`, the `if days < 1: raise HTTPException(...)` block is unreachable because `Query(..., ge=1)` validates first. Delete those two lines.

- [ ] **Step 7: Rename `_RebuildingClient` in backend conftest**

Edit `apps/backend/tests/conftest.py`. Rename `_RebuildingClient` class to `MaterializedClient` and add a class docstring:

```python
class MaterializedClient:
    """Test client that synchronously rebuilds the index cache before each call.

    Production behavior is eventually-consistent — the watcher debounces real
    filesystem events by 250ms. Tests mutate the fixture monorepo synchronously
    and expect immediate reads, so this shim forces a cache rebuild before
    every HTTP / WS operation. The real watcher path is exercised by the
    end-to-end integration test (test_integration_e2e.py).
    """
```

Also drop any unused `import os` at the top of conftest.py.

- [ ] **Step 8: Add catch-all else in lab task set_field**

Edit `apps/lab/src/lab/commands/task.py`. In `set_field`, after the existing `elif field in {"priority", "due", "status", "title"}:` branch, add:

```python
    else:
        t[field] = value
```

(This mirrors the catch-all in project.py's set_field, protecting against future additions to `_TASK_SETTABLE`.)

- [ ] **Step 9: Chain Makefile test targets**

Edit `Makefile`. Replace the `test` target with:

```makefile
test:
	@$(LAB_VENV)/bin/pytest apps/lab/tests -v && $(BACKEND_VENV)/bin/pytest apps/backend/tests -v
```

Also add a URL print to `start` and `start-bg`:

```makefile
start:
	@echo "Serving at http://localhost:3333/"
	@$(BACKEND_VENV)/bin/python -m backend

start-bg:
	@if [ -f $(PID_FILE) ] && kill -0 $$(cat $(PID_FILE)) 2>/dev/null; then \
		echo "backend already running (pid $$(cat $(PID_FILE))) — http://localhost:3333/"; \
	else \
		nohup $(BACKEND_VENV)/bin/python -m backend > .lab-backend.log 2>&1 & \
		echo $$! > $(PID_FILE); \
		echo "started backend (pid $$(cat $(PID_FILE))) — http://localhost:3333/"; \
	fi
```

- [ ] **Step 10: Run full suite**

```bash
cd /Users/jcortes/src/productivity
make test
```

Expected: 142 passing.

- [ ] **Step 11: Commit**

```bash
git add apps/ Makefile
git commit -m "chore: Plan-2 cleanup (cache root prop, broken-socket prune, cors prep, else branches, test chain)"
```

---

## Task 2: Add `CORSMiddleware` and static+template mounting

**Files:**
- Modify: `apps/backend/src/backend/main.py`
- Create: `apps/backend/src/backend/templates/index.html` (minimal skeleton)
- Create: `apps/backend/src/backend/static/.gitkeep`
- Create: `apps/backend/tests/test_cors.py`
- Create: `apps/backend/tests/test_static.py`

- [ ] **Step 1: Write minimal `index.html` skeleton**

Create `apps/backend/src/backend/templates/index.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>lab</title>
  <link rel="stylesheet" href="/static/css/app.css">
</head>
<body>
  <header>
    <h1><a href="#/">lab</a></h1>
    <nav>
      <a href="#/">Dashboard</a>
      <a href="#/timeline">Timeline</a>
    </nav>
  </header>
  <main id="view"></main>
  <script type="module" src="/static/js/app.js"></script>
</body>
</html>
```

- [ ] **Step 2: Create static placeholder**

```bash
mkdir -p /Users/jcortes/src/productivity/apps/backend/src/backend/static/css
mkdir -p /Users/jcortes/src/productivity/apps/backend/src/backend/static/js
touch /Users/jcortes/src/productivity/apps/backend/src/backend/static/.gitkeep
```

Placeholder files so StaticFiles has a directory to mount:

Create `apps/backend/src/backend/static/css/app.css`:
```css
body { font-family: system-ui, sans-serif; margin: 0; }
header { padding: 12px 24px; border-bottom: 1px solid #ddd; display: flex; gap: 24px; align-items: baseline; }
header h1 { margin: 0; font-size: 18px; }
header h1 a { color: inherit; text-decoration: none; }
header nav a { margin-right: 16px; color: #555; text-decoration: none; }
header nav a:hover { text-decoration: underline; }
main { padding: 24px; max-width: 1200px; margin: 0 auto; }
```

Create `apps/backend/src/backend/static/js/app.js`:
```javascript
// Placeholder — replaced in Task 9.
document.getElementById("view").textContent = "Loading…";
```

- [ ] **Step 3: Write failing CORS test**

Create `apps/backend/tests/test_cors.py`:

```python
def test_cors_allows_localhost_origins(client) -> None:
    r = client.get("/api/index", headers={"Origin": "http://localhost:5173"})
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_cors_preflight(client) -> None:
    r = client.options(
        "/api/index",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert r.status_code in {200, 204}
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"
```

- [ ] **Step 4: Write failing static/template test**

Create `apps/backend/tests/test_static.py`:

```python
def test_root_serves_index_html(client) -> None:
    r = client.get("/")
    assert r.status_code == 200
    assert "<title>lab</title>" in r.text
    assert 'id="view"' in r.text


def test_static_css_served(client) -> None:
    r = client.get("/static/css/app.css")
    assert r.status_code == 200
    assert "font-family" in r.text


def test_static_js_served(client) -> None:
    r = client.get("/static/js/app.js")
    assert r.status_code == 200
```

- [ ] **Step 5: Run — expect failures**

```bash
cd apps/backend
.venv/bin/pytest tests/test_cors.py tests/test_static.py -v
```

- [ ] **Step 6: Update `main.py` to mount CORS, static, and index**

Replace `apps/backend/src/backend/main.py`:

```python
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from backend import config
from backend.routes import index as index_route
from backend.routes import markdown as markdown_route
from backend.routes import project as project_route
from backend.routes import task as task_route
from backend.routes import ws as ws_route
from backend.state import IndexCache, IndexUpdatedEvent, WsBroadcaster
from backend.watcher import IndexWatcher


_PKG_DIR = Path(__file__).parent
_STATIC_DIR = _PKG_DIR / "static"
_TEMPLATES_DIR = _PKG_DIR / "templates"


@asynccontextmanager
async def lifespan(app: FastAPI):
    root = config.monorepo_root()
    cache = IndexCache(root)
    broadcaster = WsBroadcaster()

    cache.rebuild()

    import asyncio
    loop = asyncio.get_running_loop()

    def on_rebuild(_data) -> None:
        event = IndexUpdatedEvent(ts=datetime.now(tz=timezone.utc).astimezone().isoformat(timespec="seconds"))
        asyncio.run_coroutine_threadsafe(broadcaster.publish(event), loop)

    watcher = IndexWatcher(root, cache, debounce_ms=config.DEBOUNCE_MS, on_rebuild=on_rebuild)
    watcher.start()

    app.state.index_cache = cache
    app.state.ws_broadcaster = broadcaster
    app.state.index_watcher = watcher

    try:
        yield
    finally:
        watcher.stop()


def create_app() -> FastAPI:
    app = FastAPI(title="lab-backend", version="0.1.0", lifespan=lifespan)

    # Allow local dev frontends (Vite, Live Server, etc.) in addition to same-origin.
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"http://localhost(:\d+)?",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/ping")
    async def ping() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(index_route.router)
    app.include_router(project_route.router)
    app.include_router(task_route.router)
    app.include_router(markdown_route.router)
    app.include_router(ws_route.router)

    app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

    templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

    @app.get("/", response_class=HTMLResponse)
    async def index_page(request: Request):
        return templates.TemplateResponse(request, "index.html", {})

    # SPA catch-alls for client-side routes (so reloads on /p/<id> etc. work)
    @app.get("/p/{path:path}", response_class=HTMLResponse)
    async def spa_project(request: Request, path: str):
        return templates.TemplateResponse(request, "index.html", {})

    @app.get("/timeline", response_class=HTMLResponse)
    async def spa_timeline(request: Request):
        return templates.TemplateResponse(request, "index.html", {})

    @app.get("/md", response_class=HTMLResponse)
    async def spa_md(request: Request):
        return templates.TemplateResponse(request, "index.html", {})

    return app


app = create_app()


def run() -> None:
    import uvicorn

    uvicorn.run("backend.main:app", host=config.host(), port=config.port(), reload=False)
```

- [ ] **Step 7: Update backend dependencies (jinja2 comes with fastapi[all], but add explicitly)**

Edit `apps/backend/pyproject.toml`. Dependencies become:

```toml
dependencies = [
    "fastapi>=0.109",
    "uvicorn[standard]>=0.27",
    "watchdog>=4.0",
    "markdown>=3.6",
    "pyyaml>=6.0",
    "jinja2>=3.1",
    "lab",
]
```

Reinstall:
```bash
cd apps/backend
.venv/bin/pip install -e '.[dev]' --quiet
```

- [ ] **Step 8: Run — expect pass**

```bash
.venv/bin/pytest tests/test_cors.py tests/test_static.py -v
```

Expected: 5 passed.

- [ ] **Step 9: Run full backend suite**

```bash
.venv/bin/pytest -v
```

Expected: 41 passed (36 prior + 5 new).

- [ ] **Step 10: Commit**

```bash
cd /Users/jcortes/src/productivity
git add apps/backend
git commit -m "feat(backend): mount CORS + static + Jinja templates; SPA shell at /"
```

---

## Task 3: POST `/api/projects` and `/api/tasks` (mutation routes)

**Files:**
- Create: `apps/backend/src/backend/routes/mutation.py`
- Modify: `apps/backend/src/backend/main.py`
- Create: `apps/backend/tests/test_mutation_routes.py`

- [ ] **Step 1: Write failing tests**

Create `apps/backend/tests/test_mutation_routes.py`:

```python
import json


def test_post_project_new_creates_on_disk(client, monorepo) -> None:
    r = client.post("/api/projects", json={
        "id": "alpha",
        "description": "Alpha description",
        "priority": "P1",
        "tags": ["x", "y"],
        "labels": [],
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == "alpha"
    assert body["priority"] == "P1"

    on_disk = json.loads((monorepo / "content" / "projects" / "alpha" / "project.json").read_text())
    assert on_disk["description"] == "Alpha description"
    assert on_disk["tags"] == ["x", "y"]


def test_post_project_new_rejects_duplicate(client, seed_project) -> None:
    seed_project("alpha")
    r = client.post("/api/projects", json={"id": "alpha"})
    assert r.status_code == 400
    assert "already exists" in r.json()["detail"].lower()


def test_post_project_new_rejects_bad_id(client) -> None:
    r = client.post("/api/projects", json={"id": "Bad ID!"})
    assert r.status_code == 400


def test_post_task_new(client, seed_project) -> None:
    seed_project("alpha")
    r = client.post("/api/tasks", json={
        "project_id": "alpha",
        "title": "Draft",
        "priority": "P1",
        "tags": ["review"],
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == 1
    assert body["title"] == "Draft"
    assert body["status"] == "todo"


def test_post_task_status_done(client, seed_project) -> None:
    seed_project("alpha")
    client.post("/api/tasks", json={"project_id": "alpha", "title": "t", "priority": "P2"})
    r = client.post("/api/tasks/alpha/1/status", json={"status": "done"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "done"
    assert r.json()["closed_at"] is not None


def test_post_task_status_blocked_requires_reason(client, seed_project) -> None:
    seed_project("alpha")
    client.post("/api/tasks", json={"project_id": "alpha", "title": "t", "priority": "P2"})
    r = client.post("/api/tasks/alpha/1/status", json={"status": "blocked"})
    assert r.status_code == 400

    r = client.post("/api/tasks/alpha/1/status", json={"status": "blocked", "reason": "waiting on x"})
    assert r.status_code == 200
    assert r.json()["blocker"] == "waiting on x"


def test_post_task_update_field(client, seed_project) -> None:
    seed_project("alpha")
    client.post("/api/tasks", json={"project_id": "alpha", "title": "t", "priority": "P2"})
    r = client.post("/api/tasks/alpha/1/update", json={"field": "priority", "value": "P0"})
    assert r.status_code == 200
    assert r.json()["priority"] == "P0"
```

- [ ] **Step 2: Run — expect 404**

```bash
cd apps/backend
.venv/bin/pytest tests/test_mutation_routes.py -v
```

- [ ] **Step 3: Implement mutation routes**

Create `apps/backend/src/backend/routes/mutation.py`:

```python
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from lab import paths, storage
from lab.model import ModelError, _validate_id


router = APIRouter()


def _run_lab(args: list[str], *, root: Path) -> None:
    """Invoke the lab CLI with LAB_ROOT set. Raise HTTPException on non-zero."""
    import os
    env = {**os.environ, "LAB_ROOT": str(root)}
    proc = subprocess.run(
        ["lab", *args],
        env=env,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        # Strip leading "Error: " that ClickException prints.
        msg = (proc.stderr or proc.stdout).strip()
        if msg.startswith("Error: "):
            msg = msg[7:]
        raise HTTPException(status_code=400, detail=msg or "lab command failed")


def _read_project(root: Path, project_id: str) -> dict:
    pjson = paths.project_file(root, project_id)
    return storage.read_json(pjson)


def _find_task(root: Path, project_id: str, task_id: int) -> dict:
    tjson = paths.tasks_file(root, project_id)
    doc = storage.read_json(tjson)
    for t in doc.get("tasks", []):
        if t["id"] == task_id:
            return t
    raise HTTPException(status_code=404, detail=f"task #{task_id} not found")


def _validate_pid(pid: str) -> str:
    try:
        _validate_id(pid)
    except ModelError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return pid


class NewProject(BaseModel):
    id: str
    description: str = ""
    priority: str | None = None
    due: str | None = None
    tags: list[str] = Field(default_factory=list)
    labels: list[str] = Field(default_factory=list)


@router.post("/api/projects")
async def create_project(body: NewProject, request: Request) -> dict:
    root: Path = request.app.state.index_cache.root
    _validate_pid(body.id)
    args = ["project", "new", body.id]
    if body.description:
        args += ["--desc", body.description]
    if body.priority:
        args += ["--priority", body.priority]
    if body.due:
        args += ["--due", body.due]
    if body.tags:
        args += ["--tags", ",".join(body.tags)]
    if body.labels:
        args += ["--labels", ",".join(body.labels)]
    _run_lab(args, root=root)
    return _read_project(root, body.id)


class NewTask(BaseModel):
    project_id: str
    title: str
    priority: str
    loe: float | None = None
    due: str | None = None
    tags: list[str] = Field(default_factory=list)
    labels: list[str] = Field(default_factory=list)
    create_notes_file: bool = False


@router.post("/api/tasks")
async def create_task(body: NewTask, request: Request) -> dict:
    root: Path = request.app.state.index_cache.root
    _validate_pid(body.project_id)
    args = ["task", "new", body.title, "--project", body.project_id, "--priority", body.priority]
    if body.loe is not None:
        args += ["--loe", str(body.loe)]
    if body.due:
        args += ["--due", body.due]
    if body.tags:
        args += ["--tags", ",".join(body.tags)]
    if body.labels:
        args += ["--labels", ",".join(body.labels)]
    if body.create_notes_file:
        args += ["--file"]
    _run_lab(args, root=root)

    # The new task is always the last one in tasks.json
    tjson = paths.tasks_file(root, body.project_id)
    doc = storage.read_json(tjson)
    return doc["tasks"][-1]


class StatusChange(BaseModel):
    status: str  # "todo" | "in_progress" | "blocked" | "done" | "reopened"
    reason: str | None = None  # required when status == "blocked"


@router.post("/api/tasks/{project_id}/{task_id}/status")
async def set_task_status(project_id: str, task_id: int, body: StatusChange,
                          request: Request) -> dict:
    root: Path = request.app.state.index_cache.root
    _validate_pid(project_id)
    if body.status == "done":
        args = ["task", "done", str(task_id), "--project", project_id]
    elif body.status == "reopened":
        args = ["task", "reopen", str(task_id), "--project", project_id]
    elif body.status == "blocked":
        if not body.reason:
            raise HTTPException(status_code=400, detail="reason required when status=blocked")
        args = ["task", "block", str(task_id), body.reason, "--project", project_id]
    elif body.status == "in_progress":
        args = ["task", "unblock", str(task_id), "--project", project_id]
    else:
        raise HTTPException(status_code=400, detail=f"unsupported status transition: {body.status}")
    _run_lab(args, root=root)
    return _find_task(root, project_id, task_id)


class FieldUpdate(BaseModel):
    field: str
    value: str


@router.post("/api/tasks/{project_id}/{task_id}/update")
async def update_task_field(project_id: str, task_id: int, body: FieldUpdate,
                            request: Request) -> dict:
    root: Path = request.app.state.index_cache.root
    _validate_pid(project_id)
    args = ["task", "set", str(task_id), body.field, body.value, "--project", project_id]
    _run_lab(args, root=root)
    return _find_task(root, project_id, task_id)
```

- [ ] **Step 4: Wire `mutation_route` into `main.py`**

Edit `apps/backend/src/backend/main.py`. Add import:
```python
from backend.routes import mutation as mutation_route
```

Add `include_router` call after the other route includes:
```python
    app.include_router(mutation_route.router)
```

- [ ] **Step 5: Ensure `lab` is on PATH for the backend test environment**

Tests shell out to `lab`. The backend venv has lab installed in editable mode, which creates `apps/backend/.venv/bin/lab`. For the tests, ensure PATH includes the backend venv's bin dir.

Update `apps/backend/tests/conftest.py` — add to the top imports:
```python
import os
import sys
```

Update the `client` fixture to prepend the backend venv to PATH:

Find the existing `client` fixture and modify (add the PATH manipulation before creating the TestClient):

```python
@pytest.fixture()
def client(monorepo: Path):
    """FastAPI TestClient pointed at the fixture monorepo."""
    # Ensure the `lab` CLI is discoverable by subprocess.run.
    venv_bin = Path(sys.executable).parent
    os.environ["PATH"] = f"{venv_bin}:{os.environ.get('PATH', '')}"

    from backend.main import create_app
    app = create_app()
    with TestClient(app) as c:
        yield MaterializedClient(c) if "MaterializedClient" in globals() else c
```

If `MaterializedClient` is defined, keep wrapping; otherwise pass `c` through.

- [ ] **Step 6: Run — expect pass**

```bash
.venv/bin/pytest tests/test_mutation_routes.py -v
```

Expected: 7 passed.

- [ ] **Step 7: Run full suite**

```bash
.venv/bin/pytest -v
```

Expected: 48 passed (41 prior + 7 new).

- [ ] **Step 8: Commit**

```bash
cd /Users/jcortes/src/productivity
git add apps/backend
git commit -m "feat(backend): POST /api/projects, /api/tasks, /status, /update (lab CLI proxy)"
```

---

## Task 4: Frontend library (`dom.js` + `api.js`)

**Files:**
- Create: `apps/backend/src/backend/static/js/lib/dom.js`
- Create: `apps/backend/src/backend/static/js/api.js`

No Python tests for frontend code in Plan 3 — we validate through live smoke tests at the end. For now, these are building blocks used by subsequent view tasks.

- [ ] **Step 1: Write `dom.js`**

Create `apps/backend/src/backend/static/js/lib/dom.js`:

```javascript
// Tiny DOM helpers — no framework, no build step.
// h("div", {class: "row", onclick: fn}, "text", h("span", null, "nested"))

export function h(tag, attrs, ...children) {
  const el = document.createElement(tag);
  if (attrs) {
    for (const [k, v] of Object.entries(attrs)) {
      if (v == null || v === false) continue;
      if (k.startsWith("on") && typeof v === "function") {
        el.addEventListener(k.slice(2).toLowerCase(), v);
      } else if (k === "class") {
        el.className = v;
      } else if (k === "html") {
        el.innerHTML = v;
      } else if (k === "style" && typeof v === "object") {
        Object.assign(el.style, v);
      } else {
        el.setAttribute(k, v);
      }
    }
  }
  for (const child of children.flat()) {
    if (child == null || child === false) continue;
    el.appendChild(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return el;
}

export function clear(el) {
  while (el.firstChild) el.removeChild(el.firstChild);
}

export function render(parent, ...nodes) {
  clear(parent);
  for (const node of nodes) parent.appendChild(node);
}

export function fmtDate(iso) {
  if (!iso) return "—";
  return iso.slice(0, 10);
}

export function priorityClass(p) {
  return p ? `p-${p.toLowerCase()}` : "";
}
```

- [ ] **Step 2: Write `api.js`**

Create `apps/backend/src/backend/static/js/api.js`:

```javascript
// Backend API wrapper + WebSocket client.

const BASE = ""; // same origin

async function request(method, path, body) {
  const opts = { method, headers: { "Content-Type": "application/json" } };
  if (body !== undefined) opts.body = JSON.stringify(body);
  const r = await fetch(BASE + path, opts);
  if (!r.ok) {
    let detail = r.statusText;
    try {
      const j = await r.json();
      detail = j.detail || detail;
    } catch {}
    throw new Error(`${r.status}: ${detail}`);
  }
  const ct = r.headers.get("content-type") || "";
  if (ct.includes("application/json")) return r.json();
  return r.text();
}

export const api = {
  // Reads
  index: () => request("GET", "/api/index"),
  projects: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request("GET", "/api/projects" + (qs ? "?" + qs : ""));
  },
  project: (id) => request("GET", `/api/projects/${encodeURIComponent(id)}`),
  projectTasks: (id) => request("GET", `/api/projects/${encodeURIComponent(id)}/tasks`),
  projectDocs: (id) => request("GET", `/api/projects/${encodeURIComponent(id)}/docs`),
  projectFile: (id, path) =>
    request("GET", `/api/projects/${encodeURIComponent(id)}/file?path=${encodeURIComponent(path)}`),
  tasks: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request("GET", "/api/tasks" + (qs ? "?" + qs : ""));
  },
  tasksDue: (days) => request("GET", `/api/tasks/due?days=${days}`),
  markdown: (path) => request("GET", `/api/markdown?path=${encodeURIComponent(path)}`),

  // Writes
  createProject: (body) => request("POST", "/api/projects", body),
  createTask: (body) => request("POST", "/api/tasks", body),
  setTaskStatus: (projectId, taskId, body) =>
    request("POST", `/api/tasks/${encodeURIComponent(projectId)}/${taskId}/status`, body),
  updateTaskField: (projectId, taskId, body) =>
    request("POST", `/api/tasks/${encodeURIComponent(projectId)}/${taskId}/update`, body),
};

export function subscribeWS(onEvent) {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  const ws = new WebSocket(`${proto}//${location.host}/ws`);
  ws.onmessage = (ev) => {
    try {
      onEvent(JSON.parse(ev.data));
    } catch (e) {
      console.error("bad ws message", ev.data, e);
    }
  };
  ws.onerror = (e) => console.error("ws error", e);
  // Keep alive in case the server expects client messages
  ws.onopen = () => ws.send("hello");
  return ws;
}
```

- [ ] **Step 3: Commit**

```bash
cd /Users/jcortes/src/productivity
git add apps/backend/src/backend/static/js
git commit -m "feat(frontend): dom + api helper modules"
```

---

## Task 5: Frontend router + app shell

**Files:**
- Replace: `apps/backend/src/backend/static/js/app.js`

- [ ] **Step 1: Implement the router**

Replace `apps/backend/src/backend/static/js/app.js`:

```javascript
import { subscribeWS } from "./api.js";
import { clear } from "./lib/dom.js";

// Dynamic imports keep each view's code out of the initial bundle.
const routes = [
  { pattern: /^\/?$/, loader: () => import("./views/dashboard.js") },
  { pattern: /^\/p\/([^/]+)$/, loader: () => import("./views/project.js") },
  { pattern: /^\/timeline$/, loader: () => import("./views/timeline.js") },
  { pattern: /^\/md$/, loader: () => import("./views/markdown.js") },
];

let currentRender = null;

async function route() {
  const hash = location.hash.replace(/^#/, "") || "/";
  const [path, query] = hash.split("?");
  const params = new URLSearchParams(query || "");

  const view = document.getElementById("view");
  for (const { pattern, loader } of routes) {
    const match = path.match(pattern);
    if (match) {
      const mod = await loader();
      clear(view);
      currentRender = () => mod.render(view, { match, params });
      currentRender();
      return;
    }
  }

  clear(view);
  view.textContent = `No route for ${path}`;
}

window.addEventListener("hashchange", route);
window.addEventListener("DOMContentLoaded", () => {
  route();
  subscribeWS((event) => {
    if (event.type === "index-updated" && currentRender) {
      currentRender(); // re-render the current view
    }
  });
});
```

- [ ] **Step 2: Commit**

```bash
cd /Users/jcortes/src/productivity
git add apps/backend/src/backend/static/js/app.js
git commit -m "feat(frontend): hash router with dynamic view imports + WS auto-refresh"
```

---

## Task 6: Dashboard view

**Files:**
- Create: `apps/backend/src/backend/static/js/views/dashboard.js`
- Modify: `apps/backend/src/backend/static/css/app.css`

- [ ] **Step 1: Extend CSS**

APPEND to `apps/backend/src/backend/static/css/app.css`:

```css
/* Dashboard */
.due-strip {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  padding: 12px;
  background: #fffbe6;
  border: 1px solid #f0d858;
  border-radius: 6px;
  margin-bottom: 24px;
}
.due-strip:empty { display: none; }
.due-chip {
  padding: 4px 10px;
  border-radius: 12px;
  background: #fff;
  border: 1px solid #e0d06a;
  font-size: 12px;
  display: flex;
  gap: 6px;
  align-items: center;
}
.due-chip .due-date { color: #888; font-variant-numeric: tabular-nums; }

.project-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 16px;
}
.card {
  border: 1px solid #ddd;
  border-radius: 8px;
  padding: 16px;
  background: #fff;
  cursor: pointer;
  transition: box-shadow 0.1s;
}
.card:hover { box-shadow: 0 2px 8px rgba(0,0,0,0.08); }
.card h3 { margin: 0 0 8px; font-size: 16px; }
.card .desc { color: #555; font-size: 13px; margin-bottom: 8px; }
.card .counts {
  display: flex;
  gap: 10px;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}
.counts .todo { color: #555; }
.counts .in_progress { color: #2a7; }
.counts .blocked { color: #c33; }
.counts .done { color: #999; }

.chip { display: inline-block; padding: 2px 6px; border-radius: 3px; font-size: 11px; background: #eef; margin-right: 4px; }
.p-p0 { background: #fdd; color: #a00; }
.p-p1 { background: #fe9; color: #850; }
.p-p2 { background: #eef; color: #555; }
.p-p3 { background: #efe; color: #393; }

.filter-row { display: flex; gap: 8px; margin-bottom: 16px; align-items: baseline; }
.filter-row label { font-size: 13px; color: #666; }
.filter-row select { padding: 4px; }

.btn {
  border: 1px solid #aaa;
  background: #f5f5f5;
  padding: 4px 10px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
}
.btn:hover { background: #e8e8e8; }
.btn-primary { background: #2a6; color: white; border-color: #185; }
.btn-primary:hover { background: #196; }
```

- [ ] **Step 2: Implement dashboard view**

Create `apps/backend/src/backend/static/js/views/dashboard.js`:

```javascript
import { api } from "../api.js";
import { h, render, fmtDate, priorityClass } from "../lib/dom.js";

let statusFilter = "active";

export async function render(parent, _params) {
  const [idx, dueSoon] = await Promise.all([api.index(), api.tasksDue(7)]);
  const projects = idx.projects.filter((p) => statusFilter === "all" || p.status === statusFilter);

  const filterRow = h("div", { class: "filter-row" },
    h("label", null, "Show: "),
    h("select", {
      onchange: (e) => { statusFilter = e.target.value; renderView(); },
    },
      ...["active", "paused", "done", "archived", "all"].map((s) =>
        h("option", { value: s, selected: s === statusFilter ? "selected" : null }, s)
      )
    ),
    h("button", {
      class: "btn btn-primary",
      onclick: () => onNewProject(),
    }, "+ New project"),
  );

  const dueStrip = h("div", { class: "due-strip" },
    ...dueSoon.slice(0, 30).map((t) => h("span", {
      class: "due-chip",
      title: `${t.project_id}  #${t.task_id}`,
      onclick: () => { location.hash = `#/p/${t.project_id}`; },
      style: { cursor: "pointer" },
    },
      h("span", { class: "chip " + priorityClass(t.priority) }, t.priority || ""),
      h("span", null, t.title),
      h("span", { class: "due-date" }, fmtDate(t.due)),
    ))
  );

  const grid = h("div", { class: "project-grid" },
    ...projects.map((p) => projectCard(p))
  );

  render(parent,
    filterRow,
    dueSoon.length > 0 ? dueStrip : h("span"),
    projects.length > 0 ? grid : h("p", null, "No projects. Click 'New project' to create one."),
  );

  function renderView() {
    module_render(parent, _params);
  }
}

// Alias for re-render calls from within this module
const module_render = render;

function projectCard(p) {
  const counts = p.task_counts || {};
  return h("div", {
    class: "card",
    onclick: () => { location.hash = `#/p/${p.id}`; },
  },
    h("h3", null, p.id),
    p.description ? h("p", { class: "desc" }, p.description) : null,
    h("div", null,
      p.priority ? h("span", { class: "chip " + priorityClass(p.priority) }, p.priority) : null,
      p.due ? h("span", { class: "chip" }, "due " + fmtDate(p.due)) : null,
      ...(p.tags || []).map((t) => h("span", { class: "chip" }, t)),
      ...(p.labels || []).map((t) => h("span", { class: "chip" }, "@" + t)),
    ),
    h("div", { class: "counts", style: { marginTop: "8px" } },
      h("span", { class: "todo" }, `todo ${counts.todo || 0}`),
      h("span", { class: "in_progress" }, `in_progress ${counts.in_progress || 0}`),
      h("span", { class: "blocked" }, `blocked ${counts.blocked || 0}`),
      h("span", { class: "done" }, `done ${counts.done || 0}`),
    ),
  );
}

async function onNewProject() {
  const id = prompt("Project id (e.g. davi-vision):");
  if (!id) return;
  const description = prompt("Description (optional):") || "";
  const priority = prompt("Priority P0-P3 (optional):") || null;
  try {
    const p = await api.createProject({ id: id.trim(), description, priority });
    location.hash = `#/p/${p.id}`;
  } catch (e) {
    alert("Failed to create project: " + e.message);
  }
}
```

Wait — naming collision: `render` is imported AND exported. Fix: rename the exported one:

Actually the cleanest fix is to use a single function and avoid the local `module_render` alias. Rewrite:

Replace dashboard.js with:

```javascript
import { api } from "../api.js";
import { h, render as domRender, fmtDate, priorityClass } from "../lib/dom.js";

let statusFilter = "active";

export async function render(parent, params) {
  const [idx, dueSoon] = await Promise.all([api.index(), api.tasksDue(7)]);
  const projects = idx.projects.filter((p) => statusFilter === "all" || p.status === statusFilter);

  const filterRow = h("div", { class: "filter-row" },
    h("label", null, "Show: "),
    h("select", {
      onchange: (e) => { statusFilter = e.target.value; render(parent, params); },
    },
      ...["active", "paused", "done", "archived", "all"].map((s) =>
        h("option", { value: s, selected: s === statusFilter ? "selected" : null }, s)
      )
    ),
    h("button", {
      class: "btn btn-primary",
      onclick: () => onNewProject(),
    }, "+ New project"),
  );

  const dueStrip = h("div", { class: "due-strip" },
    ...dueSoon.slice(0, 30).map((t) => h("span", {
      class: "due-chip",
      title: `${t.project_id}  #${t.task_id}`,
      onclick: () => { location.hash = `#/p/${t.project_id}`; },
      style: { cursor: "pointer" },
    },
      h("span", { class: "chip " + priorityClass(t.priority) }, t.priority || ""),
      h("span", null, t.title),
      h("span", { class: "due-date" }, fmtDate(t.due)),
    ))
  );

  const grid = h("div", { class: "project-grid" },
    ...projects.map((p) => projectCard(p))
  );

  domRender(parent,
    filterRow,
    dueSoon.length > 0 ? dueStrip : h("span"),
    projects.length > 0 ? grid : h("p", null, "No projects. Click 'New project' to create one."),
  );
}

function projectCard(p) {
  const counts = p.task_counts || {};
  return h("div", {
    class: "card",
    onclick: () => { location.hash = `#/p/${p.id}`; },
  },
    h("h3", null, p.id),
    p.description ? h("p", { class: "desc" }, p.description) : null,
    h("div", null,
      p.priority ? h("span", { class: "chip " + priorityClass(p.priority) }, p.priority) : null,
      p.due ? h("span", { class: "chip" }, "due " + fmtDate(p.due)) : null,
      ...(p.tags || []).map((t) => h("span", { class: "chip" }, t)),
      ...(p.labels || []).map((t) => h("span", { class: "chip" }, "@" + t)),
    ),
    h("div", { class: "counts", style: "margin-top:8px" },
      h("span", { class: "todo" }, `todo ${counts.todo || 0}`),
      h("span", { class: "in_progress" }, `in_progress ${counts.in_progress || 0}`),
      h("span", { class: "blocked" }, `blocked ${counts.blocked || 0}`),
      h("span", { class: "done" }, `done ${counts.done || 0}`),
    ),
  );
}

async function onNewProject() {
  const id = prompt("Project id (e.g. davi-vision):");
  if (!id) return;
  const description = prompt("Description (optional):") || "";
  const priority = prompt("Priority P0-P3 (optional):") || null;
  try {
    const p = await api.createProject({ id: id.trim(), description, priority });
    location.hash = `#/p/${p.id}`;
  } catch (e) {
    alert("Failed to create project: " + e.message);
  }
}
```

- [ ] **Step 3: Commit**

```bash
cd /Users/jcortes/src/productivity
git add apps/backend/src/backend/static
git commit -m "feat(frontend): dashboard with project grid, due strip, status filter, new-project prompt"
```

---

## Task 7: Project view

**Files:**
- Create: `apps/backend/src/backend/static/js/views/project.js`
- Modify: `apps/backend/src/backend/static/css/app.css`

- [ ] **Step 1: Extend CSS**

APPEND to `apps/backend/src/backend/static/css/app.css`:

```css
/* Project view */
.proj-header { margin-bottom: 16px; }
.proj-header h2 { margin: 0 0 4px; }
.proj-header .meta { color: #666; font-size: 13px; }

.tabs { display: flex; gap: 4px; border-bottom: 1px solid #ddd; margin-bottom: 16px; }
.tab {
  padding: 8px 16px;
  border: 1px solid transparent;
  border-bottom: none;
  cursor: pointer;
  font-size: 14px;
  background: transparent;
  color: #555;
}
.tab.active {
  background: #fff;
  border-color: #ddd;
  border-bottom: 1px solid #fff;
  margin-bottom: -1px;
  color: #000;
}

table.tasks { width: 100%; border-collapse: collapse; font-size: 13px; }
table.tasks th, table.tasks td { padding: 6px 8px; text-align: left; border-bottom: 1px solid #eee; }
table.tasks th { font-weight: 600; color: #555; }
table.tasks tr:hover td { background: #fafafa; }
table.tasks .done { color: #aaa; text-decoration: line-through; }

.status-btn {
  padding: 2px 8px;
  border: 1px solid #ccc;
  background: #f8f8f8;
  border-radius: 3px;
  cursor: pointer;
  font-size: 11px;
}
.status-btn:hover { background: #eee; }

.doc-list { list-style: none; padding: 0; }
.doc-list li { padding: 6px 0; border-bottom: 1px solid #eee; font-size: 13px; }
.doc-list li a { color: #26c; text-decoration: none; }
.doc-list li a:hover { text-decoration: underline; }
```

- [ ] **Step 2: Implement project view**

Create `apps/backend/src/backend/static/js/views/project.js`:

```javascript
import { api } from "../api.js";
import { h, render as domRender, fmtDate, priorityClass } from "../lib/dom.js";

let activeTab = "tasks";

export async function render(parent, { match }) {
  const pid = decodeURIComponent(match[1]);
  const [proj, tasksDoc, docs] = await Promise.all([
    api.project(pid),
    api.projectTasks(pid),
    api.projectDocs(pid),
  ]);

  const header = h("div", { class: "proj-header" },
    h("h2", null, proj.id, " ", h("span", { class: "chip " + priorityClass(proj.priority) }, proj.priority || "")),
    h("div", { class: "meta" },
      proj.description || "(no description)",
    ),
    h("div", { class: "meta" },
      `status: ${proj.status}`,
      proj.due ? ` · due ${proj.due}` : "",
      (proj.tags || []).length ? ` · tags: ${proj.tags.join(", ")}` : "",
      (proj.labels || []).length ? ` · labels: ${proj.labels.join(", ")}` : "",
    ),
  );

  const tabs = h("div", { class: "tabs" },
    tabButton("tasks", `Tasks (${tasksDoc.tasks.length})`, parent, match),
    tabButton("docs", `Docs (${docs.length})`, parent, match),
  );

  let content;
  if (activeTab === "tasks") {
    content = tasksTable(pid, tasksDoc.tasks);
  } else {
    content = docsList(pid, docs);
  }

  domRender(parent, header, tabs, content);
}

function tabButton(key, label, parent, match) {
  return h("button", {
    class: "tab " + (activeTab === key ? "active" : ""),
    onclick: () => { activeTab = key; render(parent, { match }); },
  }, label);
}

function tasksTable(pid, tasks) {
  const newTaskBtn = h("button", {
    class: "btn btn-primary",
    onclick: () => onNewTask(pid),
    style: "margin-bottom:12px",
  }, "+ New task");

  if (!tasks.length) {
    return h("div", null, newTaskBtn, h("p", null, "No tasks yet."));
  }

  const rows = tasks.map((t) => h("tr", { class: t.status === "done" ? "done" : "" },
    h("td", null, "#" + t.id),
    h("td", null, h("span", { class: "chip " + priorityClass(t.priority) }, t.priority)),
    h("td", null, t.title),
    h("td", null, t.status + (t.blocker ? ` (${t.blocker})` : "")),
    h("td", null, fmtDate(t.due)),
    h("td", null, taskActions(pid, t)),
  ));

  const table = h("table", { class: "tasks" },
    h("thead", null, h("tr", null,
      h("th", null, "#"),
      h("th", null, "P"),
      h("th", null, "Title"),
      h("th", null, "Status"),
      h("th", null, "Due"),
      h("th", null, "Actions"),
    )),
    h("tbody", null, ...rows),
  );

  return h("div", null, newTaskBtn, table);
}

function taskActions(pid, t) {
  const actions = [];
  if (t.status === "done") {
    actions.push(statusBtn(pid, t.id, "reopened", "reopen"));
  } else {
    actions.push(statusBtn(pid, t.id, "done", "done"));
    if (t.status !== "blocked") {
      actions.push(statusBtn(pid, t.id, "blocked", "block"));
    } else {
      actions.push(statusBtn(pid, t.id, "in_progress", "unblock"));
    }
  }
  return h("span", null, ...actions);
}

function statusBtn(pid, tid, newStatus, label) {
  return h("button", {
    class: "status-btn",
    style: "margin-right:4px",
    onclick: async () => {
      try {
        let body = { status: newStatus };
        if (newStatus === "blocked") {
          const reason = prompt("Block reason:");
          if (!reason) return;
          body.reason = reason;
        }
        await api.setTaskStatus(pid, tid, body);
        // WS push triggers re-render; no manual refresh needed.
      } catch (e) {
        alert("Failed: " + e.message);
      }
    },
  }, label);
}

function docsList(pid, docs) {
  if (!docs.length) return h("p", null, "No docs, notes, or assets.");
  const items = docs.map((d) => h("li", null,
    h("a", {
      href: "#/md?path=" + encodeURIComponent(`content/projects/${pid}/${d.path}`),
    }, d.path),
    h("span", { style: "color:#999; margin-left:8px; font-size:11px" }, `${d.size} bytes`),
  ));
  return h("ul", { class: "doc-list" }, ...items);
}

async function onNewTask(pid) {
  const title = prompt("Task title:");
  if (!title) return;
  const priority = prompt("Priority P0-P3:", "P2") || "P2";
  const due = prompt("Due (YYYY-MM-DD, optional):") || null;
  try {
    await api.createTask({ project_id: pid, title: title.trim(), priority, due });
  } catch (e) {
    alert("Failed: " + e.message);
  }
}
```

- [ ] **Step 3: Commit**

```bash
cd /Users/jcortes/src/productivity
git add apps/backend/src/backend/static
git commit -m "feat(frontend): project view with tasks/docs tabs, inline status actions"
```

---

## Task 8: Markdown viewer

**Files:**
- Create: `apps/backend/src/backend/static/js/views/markdown.js`
- Modify: `apps/backend/src/backend/static/css/app.css`

- [ ] **Step 1: Extend CSS**

APPEND to `apps/backend/src/backend/static/css/app.css`:

```css
/* Markdown viewer */
.md-content {
  max-width: 800px;
  font-size: 15px;
  line-height: 1.5;
}
.md-content h1, .md-content h2, .md-content h3 { border-bottom: 1px solid #eee; padding-bottom: 4px; }
.md-content pre { background: #f6f8fa; padding: 12px; border-radius: 4px; overflow-x: auto; }
.md-content code { background: #f6f8fa; padding: 1px 4px; border-radius: 3px; font-size: 0.9em; }
.md-content pre code { background: none; padding: 0; }
.md-content table { border-collapse: collapse; margin: 12px 0; }
.md-content th, .md-content td { border: 1px solid #ddd; padding: 6px 10px; }
.md-content blockquote { border-left: 4px solid #ccc; margin: 0; padding-left: 16px; color: #555; }

.md-frontmatter {
  background: #f6f8fa;
  padding: 8px 12px;
  border-radius: 4px;
  font-family: ui-monospace, monospace;
  font-size: 12px;
  margin-bottom: 16px;
}
```

- [ ] **Step 2: Implement markdown view**

Create `apps/backend/src/backend/static/js/views/markdown.js`:

```javascript
import { api } from "../api.js";
import { h, render as domRender } from "../lib/dom.js";

export async function render(parent, { params }) {
  const path = params.get("path");
  if (!path) {
    domRender(parent, h("p", null, "Missing ?path="));
    return;
  }

  try {
    const { frontmatter, html } = await api.markdown(path);
    const fmNode = Object.keys(frontmatter || {}).length
      ? h("div", { class: "md-frontmatter" },
          JSON.stringify(frontmatter, null, 2),
        )
      : null;
    const body = h("div", { class: "md-content", html });
    domRender(parent,
      h("p", null, h("a", { href: "#", onclick: (e) => { e.preventDefault(); history.back(); } }, "← back")),
      h("h2", null, path),
      fmNode,
      body,
    );
  } catch (e) {
    domRender(parent, h("p", null, "Error: " + e.message));
  }
}
```

- [ ] **Step 3: Commit**

```bash
cd /Users/jcortes/src/productivity
git add apps/backend/src/backend/static
git commit -m "feat(frontend): markdown viewer with frontmatter display"
```

---

## Task 9: Timeline view (list + Gantt)

**Files:**
- Create: `apps/backend/src/backend/static/js/views/timeline.js`
- Modify: `apps/backend/src/backend/static/css/app.css`

- [ ] **Step 1: Extend CSS**

APPEND to `apps/backend/src/backend/static/css/app.css`:

```css
/* Timeline */
.view-toggle { margin-bottom: 16px; }
.view-toggle .pill {
  padding: 4px 12px;
  border: 1px solid #ccc;
  background: #fff;
  cursor: pointer;
  font-size: 13px;
}
.view-toggle .pill.active { background: #2a6; color: white; border-color: #185; }
.view-toggle .pill:first-child { border-radius: 4px 0 0 4px; }
.view-toggle .pill:last-child { border-radius: 0 4px 4px 0; }

.bucket { margin-bottom: 20px; }
.bucket h3 { margin: 0 0 8px; font-size: 14px; color: #666; text-transform: uppercase; letter-spacing: 0.05em; }
.bucket table { width: 100%; border-collapse: collapse; font-size: 13px; }
.bucket th, .bucket td { padding: 6px 8px; text-align: left; border-bottom: 1px solid #eee; }

.gantt { position: relative; padding: 0; }
.gantt-row { display: grid; grid-template-columns: 180px 1fr; align-items: center; padding: 4px 0; border-bottom: 1px solid #f0f0f0; }
.gantt-label { font-size: 13px; padding-right: 8px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.gantt-lane { position: relative; background: repeating-linear-gradient(90deg, #fafafa, #fafafa 30px, #f0f0f0 30px, #f0f0f0 31px); height: 18px; border-radius: 3px; }
.gantt-bar { position: absolute; top: 2px; bottom: 2px; background: #2a6; border-radius: 3px; cursor: pointer; }
.gantt-bar:hover { opacity: 0.8; }
.gantt-bar.p-p0 { background: #c33; }
.gantt-bar.p-p1 { background: #e85; }
.gantt-bar.p-p2 { background: #2a6; }
.gantt-bar.p-p3 { background: #88c; }
.gantt-bar.archived { opacity: 0.3; }
```

- [ ] **Step 2: Implement timeline view**

Create `apps/backend/src/backend/static/js/views/timeline.js`:

```javascript
import { api } from "../api.js";
import { h, render as domRender, fmtDate, priorityClass } from "../lib/dom.js";

let mode = "list"; // "list" | "gantt"

export async function render(parent, params) {
  const idx = await api.index();

  const toggle = h("div", { class: "view-toggle" },
    h("button", {
      class: "pill " + (mode === "list" ? "active" : ""),
      onclick: () => { mode = "list"; render(parent, params); },
    }, "List"),
    h("button", {
      class: "pill " + (mode === "gantt" ? "active" : ""),
      onclick: () => { mode = "gantt"; render(parent, params); },
    }, "Gantt"),
  );

  const body = mode === "list" ? renderList(idx) : renderGantt(idx);

  domRender(parent,
    h("h2", null, "Timeline"),
    toggle,
    body,
  );
}

function renderList(idx) {
  const tasks = [...idx.tasks].filter((t) => t.status !== "done");
  tasks.sort((a, b) => {
    if (a.due && b.due) return a.due.localeCompare(b.due);
    if (a.due) return -1;
    if (b.due) return 1;
    return 0;
  });

  const today = new Date().toISOString().slice(0, 10);
  const dayAfter = (d) => new Date(new Date(d).getTime() + 86400000).toISOString().slice(0, 10);
  const inDays = (n) => new Date(Date.now() + n * 86400000).toISOString().slice(0, 10);
  const buckets = {
    "Overdue": [],
    "Today / this week": [],
    "Next week": [],
    "This month": [],
    "Later": [],
    "No due date": [],
  };
  const thisWeek = inDays(7);
  const nextWeek = inDays(14);
  const thisMonth = inDays(30);

  for (const t of tasks) {
    if (!t.due) { buckets["No due date"].push(t); continue; }
    if (t.due < today) { buckets["Overdue"].push(t); continue; }
    if (t.due <= thisWeek) { buckets["Today / this week"].push(t); continue; }
    if (t.due <= nextWeek) { buckets["Next week"].push(t); continue; }
    if (t.due <= thisMonth) { buckets["This month"].push(t); continue; }
    buckets["Later"].push(t);
  }

  return h("div", null,
    ...Object.entries(buckets)
      .filter(([, rows]) => rows.length > 0)
      .map(([name, rows]) => bucket(name, rows))
  );
}

function bucket(name, rows) {
  return h("div", { class: "bucket" },
    h("h3", null, `${name} (${rows.length})`),
    h("table", null,
      h("thead", null, h("tr", null,
        h("th", null, "Due"),
        h("th", null, "P"),
        h("th", null, "Project"),
        h("th", null, "Title"),
      )),
      h("tbody", null, ...rows.map((t) => h("tr", null,
        h("td", null, fmtDate(t.due)),
        h("td", null, h("span", { class: "chip " + priorityClass(t.priority) }, t.priority)),
        h("td", null, h("a", { href: `#/p/${t.project_id}` }, t.project_id)),
        h("td", null, t.title),
      ))),
    ),
  );
}

function renderGantt(idx) {
  const projects = idx.projects.filter((p) => p.status === "active");
  if (!projects.length) return h("p", null, "No active projects.");

  // Time axis: earliest project created → 30 days past max due
  const today = new Date();
  const minD = projects.reduce((m, p) => {
    const d = p.created ? new Date(p.created) : today;
    return d < m ? d : m;
  }, today);
  const maxD = projects.reduce((m, p) => {
    const candidate = p.due ? new Date(p.due) : (p.earliest_task_due ? new Date(p.earliest_task_due) : today);
    return candidate > m ? candidate : m;
  }, new Date(today.getTime() + 14 * 86400000));

  const spanMs = Math.max(maxD - minD, 86400000);
  const pct = (d) => ((new Date(d) - minD) / spanMs) * 100;

  return h("div", { class: "gantt" },
    ...projects.map((p) => {
      const startD = p.created || today.toISOString().slice(0, 10);
      const endD = p.due || p.earliest_task_due || new Date(today.getTime() + 7 * 86400000).toISOString().slice(0, 10);
      const left = Math.max(0, pct(startD));
      const width = Math.max(1, pct(endD) - left);
      return h("div", { class: "gantt-row" },
        h("div", { class: "gantt-label" }, h("a", { href: `#/p/${p.id}` }, p.id)),
        h("div", { class: "gantt-lane" },
          h("div", {
            class: "gantt-bar " + priorityClass(p.priority) + (p.status === "archived" ? " archived" : ""),
            style: `left:${left}%; width:${width}%`,
            title: `${startD} → ${endD}`,
            onclick: () => { location.hash = `#/p/${p.id}`; },
          }),
        ),
      );
    }),
    h("p", { style: "color:#999; font-size:12px; margin-top:8px" },
      `${fmtDate(minD.toISOString())} → ${fmtDate(maxD.toISOString())}`),
  );
}
```

- [ ] **Step 3: Commit**

```bash
cd /Users/jcortes/src/productivity
git add apps/backend/src/backend/static
git commit -m "feat(frontend): timeline view with list and gantt sub-modes"
```

---

## Task 10: Final live smoke test + wrap-up

No new files. Verifies everything works end-to-end with a real backend + real browser interactions.

- [ ] **Step 1: Reinstall + run tests**

```bash
cd /Users/jcortes/src/productivity
make install
make test
```

Expected: 148 tests passing (142 Plan 2 + 6 new: CORS, static, 7 mutation routes minus any shared).

Actually the exact count is:
- Plan 2 baseline: 142
- Task 2: +5 (2 CORS + 3 static)
- Task 3: +7 (mutation routes)
- Task 1 tech-debt: no test count change (existing tests still pass; markdown test assertions loosened)
= ~154 passing.

Adjust `expected` if actual differs. No failure = success.

- [ ] **Step 2: Start backend and verify**

```bash
make start-bg
sleep 2
curl -sf http://localhost:3333/ | grep -q '<title>lab</title>' && echo "shell OK"
curl -sf http://localhost:3333/api/ping | grep -q '"status":"ok"' && echo "api OK"
curl -sf http://localhost:3333/static/js/app.js | head -3
```

- [ ] **Step 3: Open in browser**

```bash
~/.local/bin/lab open
```

This opens `http://localhost:3333/api/index` by default. Manually navigate to `http://localhost:3333/` to see the dashboard.

Alternatively use:
```bash
open http://localhost:3333/
```

Verify visually in the browser:
1. Dashboard loads, shows any existing projects or "No projects".
2. Click "+ New project", enter an id like `smoke-test`, optional description and priority. Project should appear.
3. Click into the new project. Tabs: Tasks, Docs.
4. Click "+ New task", create a task with priority P1. It appears in the table.
5. Click "done" on the task. Status changes to "done". Dashboard shows 1 done task in the project card.
6. Navigate to /timeline (click Timeline in nav). Toggle between List and Gantt.
7. Click a doc link on a project with a docs file — verify markdown renders.

- [ ] **Step 4: Cleanup**

```bash
~/.local/bin/lab project rm smoke-test --yes
make stop
```

- [ ] **Step 5: Verify clean state**

```bash
cd /Users/jcortes/src/productivity
git status
```

Expected: clean.

- [ ] **Step 6: (Optional) Commit any incidental fixes**

If the live smoke test surfaced anything that needed a fix, commit with a descriptive message.

---

## Plan 3 — Done when

1. `http://localhost:3333/` serves the SPA shell (`index.html`).
2. Dashboard shows the project grid and due-soon strip.
3. Clicking a project card navigates to `/p/<id>` and shows tasks + docs tabs.
4. Creating a task via the "+ New task" button works via POST `/api/tasks`.
5. Clicking "done" / "block" on a task updates the status; dashboard reflects immediately.
6. Timeline view shows List and Gantt sub-views.
7. Markdown viewer renders any project doc.
8. WS connection keeps views fresh across browser tabs (opening dashboard in two tabs and creating a project in one updates the other).
9. `make test` passes both suites (~154 tests).
10. Plan-2 tech-debt items 1-9 are closed.
11. Commit log tells a per-task story.

## What's NOT in Plan 3 (pointer list — remaining future work)

| Feature | Plan |
|---|---|
| Worktree commands (`lab project add/remove`) + MP prefix config | Plan 4 |
| `lab search` full-text + `/api/search` + Search view | Plan 5 |
| `lab pr add`, `lab artifact add`, `lab note` | Plan 5 |
| Migration agent for existing `~/projects/*` | Plan 6 |
| Moving `apps/darwin-runner`, `darwin-backups`, `trustim-ir-cli` into the monorepo | Plan 7 |
| Diff routes + gdiff/mdview merge into frontend | Plan 8 |
| `make seed` sample projects | Plan 9 |
| Auth, mobile layout, production deployment | Not planned |

After Plan 3 ships you have a **fully working personal productivity suite**: CLI + backend + web UI. Plans 4-9 are optional enhancements; you can stop here and still use the system productively.
