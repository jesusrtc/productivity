# Productivity Monorepo — Plan 2 (M2: Backend + Watcher + Global Index)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up a FastAPI backend that serves the monorepo's project/task/markdown content over HTTP+WS, with a file-system watcher that keeps a cached global `.index.json` in sync with on-disk changes. Fold Plan-1 tech-debt cleanups into the opening commits.

**Architecture:** A single FastAPI service on port 3333 exposes read-only `/api/*` endpoints that consume a new `lab.index` module. The index aggregates every `project.json` + `tasks.json` under `knowledge/projects/` into a single `knowledge/.index.json` (gitignored) plus an in-process cache. A `watchdog.Observer` subscribes to mutations under `knowledge/` and triggers debounced rebuilds; a WebSocket endpoint broadcasts `index-updated` events so future frontends can live-refresh. The CLI gains `lab index rebuild` (one-shot) and `lab start`/`lab stop` (service control).

**Tech Stack:** FastAPI ≥ 0.109, uvicorn ≥ 0.27, watchdog ≥ 4, httpx ≥ 0.27 (for TestClient), Python ≥ 3.11, pytest ≥ 8. Re-uses `lab` package from Plan 1 (`lab.paths`, `lab.storage`, `lab.model`).

**Out of scope for Plan 2 (deferred):**
- Any HTML/JS frontend — Plan 3 (dashboard, project view, timeline, markdown viewer UI).
- POST/PUT/DELETE API endpoints — the CLI stays the only sanctioned write path for now; web-UI mouse actions come with Plan 3 and proxy through `lab`.
- Full-text search (`lab search`, `/api/search`) — Plan 5.
- `lab project add/remove` worktree commands + `lab mp` — Plan 4.
- `lab pr add`, `lab artifact add`, `lab note` — Plan 5.
- Diff routes (`/api/diff`, commits, notebook diff) — Plan 8 (gdiff/mdview merge).
- Migration agent + `lab migrate` — Plan 6.
- Moving `apps/darwin-runner`, `apps/darwin-backups`, `apps/trustim-ir-cli` into the monorepo — Plan 7.

**By the end of Plan 2, this all works:**

```bash
# New CLI commands
lab index rebuild                            # one-shot: walks knowledge/projects/, writes knowledge/.index.json
lab start                                    # alias of `make start`; boots backend on :3333
lab stop                                     # stops running backend
lab open                                     # opens http://localhost:3333/api/index in browser

# Backend HTTP API (serves JSON)
GET  /api/index                              # full cached index (projects + tasks)
GET  /api/projects                           # index slice: just projects (optional ?status=active)
GET  /api/projects/{id}                      # full project.json
GET  /api/projects/{id}/tasks                # full tasks.json
GET  /api/projects/{id}/docs                 # list of md/assets paths under the project
GET  /api/projects/{id}/file?path=...        # raw file body (text or binary)
GET  /api/tasks                              # flat task list from index (filter by query)
GET  /api/tasks/due?days=N                   # upcoming-due slice

GET  /api/markdown?path=knowledge/...        # render any md under knowledge/ → {frontmatter, html}

# WebSocket
WS   /ws                                     # broadcasts {"type":"index-updated","ts":<iso>} on every rebuild

# Lifecycle
make start        # uvicorn :3333, watcher running
make stop         # kills running backend
make test         # runs lab + backend pytest suites
```

Plus the following tech-debt cleanups ship early in the plan:
- `_resolve_project_id` deduplicated into `lab.paths.find_project_id_from_pwd`.
- `split_csv` moved into a shared `lab.util` module.
- Every project/task command now calls `_validate_id` on its `project_id` argument (prevents path-traversal sharp edges flagged in T14 review).
- `project new` is atomic: on any failure mid-creation, the partially-built project dir is removed.
- `project set` and `task set` trap `ValueError` from `float(loe)` and surface a clean `ClickException` instead of a raw traceback.
- Missing filter tests for `project ls --tag/--label` and `task ls --tag/--label/--due <bad>` are added.

---

## File Structure

### New files (created in this plan)

```
apps/lab/
├── src/lab/
│   ├── util.py                  # shared helpers (split_csv)
│   ├── index.py                 # build_index, write_index, read_index, Index dataclass
│   └── commands/
│       ├── index.py             # `lab index rebuild` CLI
│       └── service.py           # `lab start`, `lab stop`, `lab open` CLI wrappers
└── tests/
    ├── test_util.py
    ├── test_index.py
    └── test_cli_index.py

apps/backend/                     # NEW package
├── pyproject.toml
├── README.md
├── backend                       # shell shim → python -m backend
├── src/backend/
│   ├── __init__.py               # __version__
│   ├── __main__.py               # python -m backend → uvicorn
│   ├── main.py                   # FastAPI app factory + lifespan
│   ├── state.py                  # IndexCache + WS broadcaster (in-memory singletons)
│   ├── watcher.py                # watchdog.Observer wrapper with 250ms debounce
│   ├── config.py                 # host/port/root, reads LAB_ROOT
│   └── routes/
│       ├── __init__.py
│       ├── index.py              # GET /api/index
│       ├── project.py            # GET /api/projects[...]
│       ├── task.py               # GET /api/tasks[...]
│       ├── markdown.py           # GET /api/markdown
│       └── ws.py                 # WS /ws
└── tests/
    ├── conftest.py               # `client` fixture, re-uses `monorepo` / `seed_project` from lab
    ├── test_health.py            # trivial /api/ping
    ├── test_index_route.py
    ├── test_project_routes.py
    ├── test_task_routes.py
    ├── test_markdown_route.py
    ├── test_watcher.py
    ├── test_ws.py
    └── test_integration_e2e.py
```

### Modified files (Plan 1 cleanup, bundled in Task 1)

```
apps/lab/src/lab/paths.py                    # add find_project_id_from_pwd + ProjectNotFound
apps/lab/src/lab/commands/project.py         # use shared helpers; id validation on every command; atomic new; loe wrap
apps/lab/src/lab/commands/task.py            # use shared helpers; id validation on every command; loe wrap
apps/lab/tests/test_cli_project.py           # +missing tests (tag/label filters on ls)
apps/lab/tests/test_cli_task.py              # +missing tests (tag/label filters; --due bad format)
apps/lab/tests/test_storage.py               # +cleanup-on-failure fault injection test
Makefile                                     # new `start`, `stop`, `start-bg` targets; `test` runs both suites
.gitignore                                   # add apps/backend/.venv, apps/backend/.coverage
```

### Responsibilities per new file

- `lab.util` — misc helpers that don't belong to a domain module. Initially just `split_csv`.
- `lab.index` — **single source of truth for index shape**. `build_index(root)` walks projects, returns a dict matching the spec's §5.4 format. `write_index(root, data)` persists. `read_index(root)` loads (or triggers rebuild if missing).
- `lab.commands.index` — thin CLI wrapper: `lab index rebuild`, `lab index show`.
- `lab.commands.service` — CLI wrappers for start/stop/open; shell out to make / pkill / webbrowser.
- `backend.main` — FastAPI factory + lifespan: on startup, build index, start watcher, register route modules.
- `backend.state` — `IndexCache` singleton (in-memory dict + read lock) and `WsBroadcaster` singleton (list of WebSocket connections, publish method).
- `backend.watcher` — `IndexWatcher` class: wraps `watchdog.Observer`, debounces bursts, triggers `rebuild()` which updates disk + cache + broadcasts.
- `backend.config` — reads `LAB_ROOT` (default: monorepo root via `lab.paths.find_monorepo_root`), exposes `HOST`, `PORT`, `DEBOUNCE_MS`.
- `backend.routes.*` — one file per route group. Each returns JSON from the cache; markdown route reads files directly.

---

## Task 1: Plan-1 tech-debt cleanup

**Files:**
- Modify: `apps/lab/src/lab/paths.py`
- Create: `apps/lab/src/lab/util.py`
- Modify: `apps/lab/src/lab/commands/project.py`
- Modify: `apps/lab/src/lab/commands/task.py`
- Modify: `apps/lab/tests/test_cli_project.py`
- Modify: `apps/lab/tests/test_cli_task.py`
- Modify: `apps/lab/tests/test_storage.py`
- Create: `apps/lab/tests/test_util.py`

This task bundles six cleanups called out in Plan-1's final review. Each is a tiny change; the total stays well under a normal Task's footprint because every sub-change has an existing or trivial test.

- [ ] **Step 1: Create `apps/lab/src/lab/util.py`**

```python
from __future__ import annotations


def split_csv(value: str | None) -> list[str]:
    """Parse a comma-separated string into a list of stripped non-empty values.

    Examples:
        split_csv("a,b,c")        -> ["a", "b", "c"]
        split_csv("  a , , b  ")  -> ["a", "b"]
        split_csv(None)           -> []
        split_csv("")             -> []
    """
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()]
```

- [ ] **Step 2: Create `apps/lab/tests/test_util.py`**

```python
from __future__ import annotations

import pytest

from lab.util import split_csv


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("", []),
        (None, []),
        ("a", ["a"]),
        ("a,b,c", ["a", "b", "c"]),
        ("  a , b ,  c ", ["a", "b", "c"]),
        ("a,,b", ["a", "b"]),
        (",a,b,", ["a", "b"]),
        ("a, ,b", ["a", "b"]),
    ],
)
def test_split_csv(raw: str | None, expected: list[str]) -> None:
    assert split_csv(raw) == expected
```

- [ ] **Step 3: Run util tests**

```bash
cd apps/lab
.venv/bin/pytest tests/test_util.py -v
```

Expected: 8 parametrized cases pass.

- [ ] **Step 4: Add `find_project_id_from_pwd` to `apps/lab/src/lab/paths.py`**

APPEND to `paths.py` (after `tasks_file`):

```python


class ProjectNotFound(RuntimeError):
    """Raised when PWD is not inside any project under knowledge/projects/."""


def find_project_id_from_pwd(root: Path, start: Path | None = None) -> str:
    """Walk up from `start` (defaults to PWD) to find the project folder.

    Returns the project id (the directory name whose parent is
    `<root>/knowledge/projects/`). Raises `ProjectNotFound` if the walk
    reaches `root` without finding a project folder.
    """
    projects_root = (root / "knowledge" / "projects").resolve()
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if candidate.parent == projects_root:
            return candidate.name
        if candidate == root.resolve():
            break
    raise ProjectNotFound(
        "no project — pass --project <id> or cd into a project folder"
    )
```

- [ ] **Step 5: Add tests for `find_project_id_from_pwd`**

APPEND to `apps/lab/tests/test_paths.py`:

```python


from lab.paths import ProjectNotFound, find_project_id_from_pwd


def test_find_project_id_from_pwd_inside_project(monorepo: Path, seed_project, monkeypatch) -> None:
    pdir = seed_project("alpha")
    monkeypatch.chdir(pdir)
    assert find_project_id_from_pwd(monorepo) == "alpha"


def test_find_project_id_from_pwd_inside_subdir(monorepo: Path, seed_project, monkeypatch) -> None:
    pdir = seed_project("alpha")
    (pdir / "docs" / "nested").mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(pdir / "docs" / "nested")
    assert find_project_id_from_pwd(monorepo) == "alpha"


def test_find_project_id_from_pwd_outside_raises(monorepo: Path, monkeypatch) -> None:
    monkeypatch.chdir(monorepo)
    with pytest.raises(ProjectNotFound):
        find_project_id_from_pwd(monorepo)
```

- [ ] **Step 6: Refactor `commands/project.py` to use shared helpers + add id validation + atomic new + `loe` trap**

The full replacement for `apps/lab/src/lab/commands/project.py` is:

```python
from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path

import click

from lab import paths, storage
from lab.model import ModelError, Priority, Project, ProjectStatus, _validate_id
from lab.util import split_csv


_CLAUDE_TEMPLATE = """# {name}

## Objective
{description}

## On session start
Run `lab project status` for current state.
Check the dashboard at http://localhost:3333/p/{id} (Plan 2+).

## Task operations
Use `lab task ...`. Current tasks: `lab task ls`.

## Available tools (populated in later plans)
- `apps/darwin-runner` — matplotlib charts on Darwin kernel
- `apps/darwin-backups q "…"` — query past notebooks
- `apps/trustim-ir-cli` — inResponse queries

Shared agents at repo root `.claude/agents/`. Templates at `knowledge/skills/`.
"""


_PROJECT_SETTABLE = {
    "description", "status", "priority", "due", "loe", "tags", "labels", "name",
}


def _require_valid_id(project_id: str) -> str:
    """Validate `project_id` and surface ModelError as ClickException."""
    try:
        return _validate_id(project_id)
    except ModelError as exc:
        raise click.ClickException(str(exc)) from exc


def _iter_project_files(root: Path):
    projects_root = root / "knowledge" / "projects"
    if not projects_root.is_dir():
        return
    for child in sorted(projects_root.iterdir()):
        pjson = child / "project.json"
        if pjson.is_file():
            yield pjson


@click.group(name="project")
def project_group() -> None:
    """Project lifecycle commands."""


@project_group.command("new")
@click.argument("project_id")
@click.option("--desc", "description", default="", help="Short description")
@click.option("--priority", type=click.Choice([p.value for p in Priority]), default=None)
@click.option("--due", default=None, help="Due date YYYY-MM-DD")
@click.option("--tags", default="", help="Comma-separated tags")
@click.option("--labels", default="", help="Comma-separated MP labels")
def new(project_id: str, description: str, priority: str | None, due: str | None,
        tags: str, labels: str) -> None:
    """Create a new project under knowledge/projects/<id>/."""
    root = paths.find_monorepo_root()
    try:
        project = Project.from_dict({
            "id": project_id,
            "name": project_id,
            "description": description,
            "status": "active",
            "priority": priority,
            "due": due,
            "tags": split_csv(tags),
            "labels": split_csv(labels),
        })
    except ModelError as exc:
        raise click.ClickException(str(exc)) from exc

    pdir = paths.project_dir(root, project.id)
    if pdir.exists():
        raise click.ClickException(f"project {project.id!r} already exists at {pdir}")

    # Atomic creation: if any step fails, remove the partial directory.
    try:
        (pdir / "docs").mkdir(parents=True)
        (pdir / "notes").mkdir()
        (pdir / "assets").mkdir()

        storage.write_json(paths.project_file(root, project.id), project.to_dict())
        storage.write_json(paths.tasks_file(root, project.id), {"next_id": 1, "tasks": []})

        (pdir / "CLAUDE.md").write_text(
            _CLAUDE_TEMPLATE.format(
                id=project.id,
                name=project.name,
                description=project.description or "(not yet defined — set with `lab project set <id> description \"...\"`)",
            ),
            encoding="utf-8",
        )
    except Exception:
        if pdir.exists():
            shutil.rmtree(pdir, ignore_errors=True)
        raise

    click.echo(f"created {project.id} at {pdir}")


@project_group.command("ls")
@click.option("--status", type=click.Choice([s.value for s in ProjectStatus]), default=None)
@click.option("--tag", "tag_filter", default=None)
@click.option("--label", "label_filter", default=None)
def ls(status: str | None, tag_filter: str | None, label_filter: str | None) -> None:
    """List projects (default: all)."""
    root = paths.find_monorepo_root()
    rows = []
    for pjson in _iter_project_files(root):
        data = storage.read_json(pjson)
        if status and data.get("status") != status:
            continue
        if tag_filter and tag_filter not in (data.get("tags") or []):
            continue
        if label_filter and label_filter not in (data.get("labels") or []):
            continue
        rows.append(data)

    if not rows:
        click.echo("no projects")
        return

    width_id = max(len(r["id"]) for r in rows)
    for r in rows:
        priority = r.get("priority") or "--"
        due = r.get("due") or "--"
        desc = (r.get("description") or "").strip().split("\n")[0][:60]
        click.echo(f"{r['id']:<{width_id}}  {r['status']:<8}  {priority:<2}  {due:<10}  {desc}")


@project_group.command("status")
@click.argument("project_id", required=False)
def status(project_id: str | None) -> None:
    """Print a summary of a project (uses PWD if no id given)."""
    root = paths.find_monorepo_root()
    if project_id:
        pid = _require_valid_id(project_id)
    else:
        try:
            pid = paths.find_project_id_from_pwd(root)
        except paths.ProjectNotFound as exc:
            raise click.ClickException(str(exc)) from exc

    pjson = paths.project_file(root, pid)
    if not pjson.is_file():
        raise click.ClickException(f"project {pid!r} not found")
    data = storage.read_json(pjson)

    tjson = paths.tasks_file(root, pid)
    task_counts = {"todo": 0, "in_progress": 0, "blocked": 0, "done": 0}
    if tjson.is_file():
        for t in storage.read_json(tjson).get("tasks", []):
            s = t.get("status")
            if s in task_counts:
                task_counts[s] += 1

    click.echo(f"{data['id']}  ({data['status']})")
    if data.get("description"):
        for line in data["description"].splitlines():
            click.echo(f"  {line}")
    click.echo(
        f"  tasks: todo={task_counts['todo']} in_progress={task_counts['in_progress']} "
        f"blocked={task_counts['blocked']} done={task_counts['done']}"
    )
    if data.get("priority"):
        click.echo(f"  priority: {data['priority']}")
    if data.get("due"):
        click.echo(f"  due: {data['due']}")
    if data.get("tags"):
        click.echo(f"  tags: {', '.join(data['tags'])}")
    if data.get("labels"):
        click.echo(f"  labels: {', '.join(data['labels'])}")


@project_group.command("set")
@click.argument("project_id")
@click.argument("field")
@click.argument("value")
def set_field(project_id: str, field: str, value: str) -> None:
    """Update a single field on a project (validated)."""
    pid = _require_valid_id(project_id)
    if field not in _PROJECT_SETTABLE:
        raise click.ClickException(
            f"{field} is not settable. Allowed: {sorted(_PROJECT_SETTABLE)}"
        )
    root = paths.find_monorepo_root()
    pjson = paths.project_file(root, pid)
    if not pjson.is_file():
        raise click.ClickException(f"project {pid!r} not found")
    data = storage.read_json(pjson)

    if field in {"tags", "labels"}:
        data[field] = split_csv(value)
    elif field == "loe":
        if value in {"", "null", "none"}:
            data[field] = None
        else:
            try:
                data[field] = float(value)
            except ValueError as exc:
                raise click.ClickException(f"loe: {value!r} is not a number") from exc
    elif field in {"priority", "due", "status"}:
        data[field] = value if value not in {"", "null", "none"} else None
    else:
        data[field] = value

    data["updated"] = date.today().isoformat()

    try:
        Project.from_dict(data)
    except ModelError as exc:
        raise click.ClickException(str(exc)) from exc

    storage.write_json(pjson, data)
    click.echo(f"{pid}.{field} = {data[field]!r}")


@project_group.command("archive")
@click.argument("project_id")
def archive(project_id: str) -> None:
    """Set status to archived (hidden from default dashboard)."""
    pid = _require_valid_id(project_id)
    root = paths.find_monorepo_root()
    pjson = paths.project_file(root, pid)
    if not pjson.is_file():
        raise click.ClickException(f"project {pid!r} not found")
    data = storage.read_json(pjson)
    data["status"] = "archived"
    data["updated"] = date.today().isoformat()

    try:
        Project.from_dict(data)
    except ModelError as exc:
        raise click.ClickException(str(exc)) from exc

    storage.write_json(pjson, data)
    click.echo(f"archived {pid}")


@project_group.command("rm")
@click.argument("project_id")
@click.option("--yes", is_flag=True, help="Skip confirmation")
def rm(project_id: str, yes: bool) -> None:
    """Delete a project folder permanently. Worktrees, if any, must be removed first (later plan)."""
    pid = _require_valid_id(project_id)
    root = paths.find_monorepo_root()
    pdir = paths.project_dir(root, pid)
    if not pdir.is_dir():
        raise click.ClickException(f"project {pid!r} not found")

    if not yes:
        click.confirm(
            f"Permanently delete {pdir}? This cannot be undone.",
            abort=True,
        )

    shutil.rmtree(pdir)
    click.echo(f"removed {pid}")
```

- [ ] **Step 7: Refactor `commands/task.py` to use shared helpers + add id validation + `loe` trap**

The full replacement for `apps/lab/src/lab/commands/task.py`:

```python
from __future__ import annotations

import re
from datetime import date, datetime, timezone
from pathlib import Path

import click

from lab import paths, storage
from lab.model import ModelError, Priority, Task, _validate_id
from lab.util import split_csv


_SLUG_RE = re.compile(r"[^a-z0-9]+")
_TASK_SETTABLE = {"title", "priority", "loe", "due", "tags", "labels", "status"}


def _slugify(title: str) -> str:
    return _SLUG_RE.sub("-", title.lower()).strip("-")[:40] or "task"


def _require_valid_id(project_id: str) -> str:
    try:
        return _validate_id(project_id)
    except ModelError as exc:
        raise click.ClickException(str(exc)) from exc


def _resolve_project_id(explicit: str | None) -> str:
    if explicit:
        return _require_valid_id(explicit)
    root = paths.find_monorepo_root()
    try:
        return paths.find_project_id_from_pwd(root)
    except paths.ProjectNotFound as exc:
        raise click.ClickException(str(exc)) from exc


def _load_tasks(root: Path, project_id: str) -> dict:
    tjson = paths.tasks_file(root, project_id)
    if not tjson.is_file():
        raise click.ClickException(f"project {project_id!r} has no tasks.json")
    return storage.read_json(tjson)


def _save_tasks(root: Path, project_id: str, data: dict) -> None:
    storage.write_json(paths.tasks_file(root, project_id), data)


def _find_task(tasks_doc: dict, task_id: int) -> dict:
    for t in tasks_doc.get("tasks", []):
        if t["id"] == task_id:
            return t
    raise click.ClickException(f"task #{task_id} not found")


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).astimezone().isoformat(timespec="seconds")


def _iter_all_tasks(root: Path):
    projects_root = root / "knowledge" / "projects"
    if not projects_root.is_dir():
        return
    for child in sorted(projects_root.iterdir()):
        tjson = child / "tasks.json"
        if not tjson.is_file():
            continue
        doc = storage.read_json(tjson)
        for t in doc.get("tasks", []):
            yield child.name, t


def _parse_due_window(value: str) -> int:
    m = re.fullmatch(r"(\d+)d", value)
    if not m:
        raise click.ClickException(f"--due must be Nd (e.g. 7d); got {value!r}")
    return int(m.group(1))


@click.group(name="task")
def task_group() -> None:
    """Task lifecycle commands."""


@task_group.command("new")
@click.argument("title")
@click.option("--project", "project_id", default=None)
@click.option("--priority", type=click.Choice([p.value for p in Priority]), required=True)
@click.option("--loe", type=float, default=None)
@click.option("--due", default=None)
@click.option("--tags", default="")
@click.option("--labels", default="")
@click.option("--file", "create_file", is_flag=True, default=False, help="Create a notes md file")
def new(title: str, project_id: str | None, priority: str, loe: float | None,
        due: str | None, tags: str, labels: str, create_file: bool) -> None:
    """Create a new task in a project (default: PWD project)."""
    root = paths.find_monorepo_root()
    pid = _resolve_project_id(project_id)
    pjson = paths.project_file(root, pid)
    if not pjson.is_file():
        raise click.ClickException(f"project {pid!r} not found")

    tasks_doc = _load_tasks(root, pid)
    task_id = int(tasks_doc.get("next_id", 1))
    slug = _slugify(title)
    notes_file = None
    if create_file:
        notes_rel = f"notes/{task_id:03d}-{slug}.md"
        notes_path = paths.project_dir(root, pid) / notes_rel
        notes_path.parent.mkdir(parents=True, exist_ok=True)
        if not notes_path.exists():
            notes_path.write_text(f"# {title}\n\n", encoding="utf-8")
        notes_file = notes_rel

    try:
        task = Task.from_dict({
            "id": task_id,
            "title": title,
            "status": "todo",
            "priority": priority,
            "loe": loe,
            "due": due,
            "tags": split_csv(tags),
            "labels": split_csv(labels),
            "notes_file": notes_file,
        })
    except ModelError as exc:
        raise click.ClickException(str(exc)) from exc

    tasks_doc["tasks"].append(task.to_dict())
    tasks_doc["next_id"] = task_id + 1
    _save_tasks(root, pid, tasks_doc)

    click.echo(f"{pid}#{task_id}  {title}")


@task_group.command("ls")
@click.option("--project", "project_id", default=None)
@click.option("--status", default=None, help="todo|in_progress|blocked|done|open (= not done)")
@click.option("--priority", default=None, help="Comma-separated (e.g. P0,P1)")
@click.option("--tag", "tag_filter", default=None)
@click.option("--label", "label_filter", default=None)
@click.option("--due", "due_window", default=None, help="Nd — due within N days")
def ls(project_id: str | None, status: str | None, priority: str | None,
       tag_filter: str | None, label_filter: str | None,
       due_window: str | None) -> None:
    """List tasks. Default: all projects. Filter with --project, --status, --priority, --tag, --label, --due."""
    from datetime import timedelta

    root = paths.find_monorepo_root()

    if project_id:
        pid = _require_valid_id(project_id)
        it = ((pid, t) for t in _load_tasks(root, pid).get("tasks", []))
    else:
        it = _iter_all_tasks(root)

    pr_set = set(split_csv(priority)) if priority else None
    horizon = None
    if due_window:
        days = _parse_due_window(due_window)
        horizon = date.today() + timedelta(days=days)

    rows = []
    for pid, t in it:
        if status == "open":
            if t["status"] == "done":
                continue
        elif status:
            if t["status"] != status:
                continue
        if pr_set and t["priority"] not in pr_set:
            continue
        if tag_filter and tag_filter not in (t.get("tags") or []):
            continue
        if label_filter and label_filter not in (t.get("labels") or []):
            continue
        if horizon:
            due = t.get("due")
            if not due or date.fromisoformat(due) > horizon:
                continue
        rows.append((pid, t))

    if not rows:
        click.echo("no tasks")
        return

    w_pid = max(len(pid) for pid, _ in rows)
    for pid, t in rows:
        due = t.get("due") or "--"
        click.echo(
            f"{pid:<{w_pid}}  #{t['id']:<3}  {t['status']:<11}  {t['priority']}  {due:<10}  {t['title']}"
        )


@task_group.command("done")
@click.argument("task_id", type=int)
@click.option("--project", "project_id", default=None)
def done(task_id: int, project_id: str | None) -> None:
    """Mark a task done (sets closed_at)."""
    root = paths.find_monorepo_root()
    pid = _resolve_project_id(project_id)
    doc = _load_tasks(root, pid)
    t = _find_task(doc, task_id)
    t["status"] = "done"
    t["closed_at"] = _now_iso()
    t["updated"] = date.today().isoformat()
    _save_tasks(root, pid, doc)
    click.echo(f"{pid}#{task_id}  done")


@task_group.command("reopen")
@click.argument("task_id", type=int)
@click.option("--project", "project_id", default=None)
def reopen(task_id: int, project_id: str | None) -> None:
    """Reopen a done task (status → in_progress, clears closed_at)."""
    root = paths.find_monorepo_root()
    pid = _resolve_project_id(project_id)
    doc = _load_tasks(root, pid)
    t = _find_task(doc, task_id)
    t["status"] = "in_progress"
    t["closed_at"] = None
    t["updated"] = date.today().isoformat()
    _save_tasks(root, pid, doc)
    click.echo(f"{pid}#{task_id}  reopened")


@task_group.command("block")
@click.argument("task_id", type=int)
@click.argument("reason")
@click.option("--project", "project_id", default=None)
def block(task_id: int, reason: str, project_id: str | None) -> None:
    """Mark a task blocked with a reason."""
    root = paths.find_monorepo_root()
    pid = _resolve_project_id(project_id)
    doc = _load_tasks(root, pid)
    t = _find_task(doc, task_id)
    t["status"] = "blocked"
    t["blocker"] = reason
    t["updated"] = date.today().isoformat()
    _save_tasks(root, pid, doc)
    click.echo(f"{pid}#{task_id}  blocked: {reason}")


@task_group.command("unblock")
@click.argument("task_id", type=int)
@click.option("--project", "project_id", default=None)
def unblock(task_id: int, project_id: str | None) -> None:
    """Clear a task's blocker (status → in_progress)."""
    root = paths.find_monorepo_root()
    pid = _resolve_project_id(project_id)
    doc = _load_tasks(root, pid)
    t = _find_task(doc, task_id)
    t["status"] = "in_progress"
    t["blocker"] = None
    t["updated"] = date.today().isoformat()
    _save_tasks(root, pid, doc)
    click.echo(f"{pid}#{task_id}  unblocked")


@task_group.command("show")
@click.argument("task_id", type=int)
@click.option("--project", "project_id", default=None)
def show(task_id: int, project_id: str | None) -> None:
    """Print a task's fields and notes file content (if any)."""
    import json as _json

    root = paths.find_monorepo_root()
    pid = _resolve_project_id(project_id)
    doc = _load_tasks(root, pid)
    t = _find_task(doc, task_id)
    click.echo(_json.dumps(t, indent=2))
    notes_file = t.get("notes_file")
    if notes_file:
        notes_path = paths.project_dir(root, pid) / notes_file
        if notes_path.is_file():
            click.echo("")
            click.echo(f"--- {notes_file} ---")
            click.echo(notes_path.read_text())


@task_group.command("set")
@click.argument("task_id", type=int)
@click.argument("field")
@click.argument("value")
@click.option("--project", "project_id", default=None)
def set_field(task_id: int, field: str, value: str, project_id: str | None) -> None:
    """Update a single task field (validated)."""
    if field not in _TASK_SETTABLE:
        raise click.ClickException(
            f"{field} is not settable. Allowed: {sorted(_TASK_SETTABLE)}"
        )
    root = paths.find_monorepo_root()
    pid = _resolve_project_id(project_id)
    doc = _load_tasks(root, pid)
    t = _find_task(doc, task_id)

    if field in {"tags", "labels"}:
        t[field] = split_csv(value)
    elif field == "loe":
        if value in {"", "null", "none"}:
            t[field] = None
        else:
            try:
                t[field] = float(value)
            except ValueError as exc:
                raise click.ClickException(f"loe: {value!r} is not a number") from exc
    elif field in {"priority", "due", "status", "title"}:
        t[field] = value

    t["updated"] = date.today().isoformat()

    try:
        Task.from_dict(t)
    except ModelError as exc:
        raise click.ClickException(str(exc)) from exc

    _save_tasks(root, pid, doc)
    click.echo(f"{pid}#{task_id}.{field} = {t[field]!r}")
```

- [ ] **Step 8: Add missing filter tests to `apps/lab/tests/test_cli_project.py`**

APPEND to `test_cli_project.py`:

```python


def test_project_ls_filter_by_tag(monorepo: Path, seed_project) -> None:
    alpha = seed_project("alpha")
    seed_project("beta")
    data = json.loads((alpha / "project.json").read_text())
    data["tags"] = ["backend"]
    (alpha / "project.json").write_text(json.dumps(data))

    runner = CliRunner()
    result = runner.invoke(main, ["project", "ls", "--tag", "backend"])
    assert result.exit_code == 0
    assert "alpha" in result.output
    assert "beta" not in result.output


def test_project_ls_filter_by_label(monorepo: Path, seed_project) -> None:
    seed_project("alpha")
    beta = seed_project("beta")
    data = json.loads((beta / "project.json").read_text())
    data["labels"] = ["lipy-davi"]
    (beta / "project.json").write_text(json.dumps(data))

    runner = CliRunner()
    result = runner.invoke(main, ["project", "ls", "--label", "lipy-davi"])
    assert result.exit_code == 0
    assert "beta" in result.output
    assert "alpha" not in result.output


def test_project_set_loe_invalid(monorepo: Path, seed_project) -> None:
    seed_project("alpha")
    runner = CliRunner()
    result = runner.invoke(main, ["project", "set", "alpha", "loe", "not-a-number"])
    assert result.exit_code != 0
    assert "not a number" in result.output.lower()


def test_project_new_is_atomic_on_failure(monorepo: Path, monkeypatch) -> None:
    """If storage.write_json fails mid-creation, no partial pdir is left behind."""
    import lab.storage as storage_mod
    original_write = storage_mod.write_json
    calls = {"n": 0}

    def flaky(path, data):
        calls["n"] += 1
        if calls["n"] == 2:  # fail on the second write (tasks.json)
            raise OSError("disk went away")
        return original_write(path, data)

    monkeypatch.setattr(storage_mod, "write_json", flaky)

    runner = CliRunner()
    result = runner.invoke(main, ["project", "new", "doomed", "--desc", "test"])
    assert result.exit_code != 0
    assert not (monorepo / "knowledge" / "projects" / "doomed").exists()
```

- [ ] **Step 9: Add missing filter tests to `apps/lab/tests/test_cli_task.py`**

APPEND to `test_cli_task.py`:

```python


def test_task_ls_filter_by_tag(monorepo: Path, seed_project) -> None:
    seed_project("alpha")
    runner = CliRunner()
    runner.invoke(main, ["task", "new", "reviewed", "--project", "alpha", "--priority", "P2", "--tags", "review"])
    runner.invoke(main, ["task", "new", "other", "--project", "alpha", "--priority", "P2"])
    result = runner.invoke(main, ["task", "ls", "--tag", "review"])
    assert result.exit_code == 0
    assert "reviewed" in result.output
    assert "other" not in result.output


def test_task_ls_filter_by_label(monorepo: Path, seed_project) -> None:
    seed_project("alpha")
    runner = CliRunner()
    runner.invoke(main, ["task", "new", "labeled", "--project", "alpha", "--priority", "P2", "--labels", "lipy-davi"])
    runner.invoke(main, ["task", "new", "other", "--project", "alpha", "--priority", "P2"])
    result = runner.invoke(main, ["task", "ls", "--label", "lipy-davi"])
    assert result.exit_code == 0
    assert "labeled" in result.output
    assert "other" not in result.output


def test_task_ls_due_bad_format(monorepo: Path, seed_project) -> None:
    seed_project("alpha")
    runner = CliRunner()
    runner.invoke(main, ["task", "new", "t", "--project", "alpha", "--priority", "P2"])
    result = runner.invoke(main, ["task", "ls", "--project", "alpha", "--due", "foo"])
    assert result.exit_code != 0
    assert "nd" in result.output.lower()


def test_task_set_loe_invalid(monorepo: Path, seed_project) -> None:
    seed_project("alpha")
    runner = CliRunner()
    runner.invoke(main, ["task", "new", "t", "--project", "alpha", "--priority", "P2"])
    result = runner.invoke(main, ["task", "set", "1", "loe", "abc", "--project", "alpha"])
    assert result.exit_code != 0
    assert "not a number" in result.output.lower()
```

- [ ] **Step 10: Add fault-injection test to `apps/lab/tests/test_storage.py`**

APPEND to `test_storage.py`:

```python


def test_write_json_cleans_up_temp_on_failure(tmp_path: Path) -> None:
    """A non-serializable payload raises and leaves no temp file behind."""
    class Unserializable:
        pass

    target = tmp_path / "out.json"
    with pytest.raises(TypeError):
        write_json(target, {"bad": Unserializable()})

    siblings = list(tmp_path.iterdir())
    assert siblings == [], f"unexpected files: {siblings}"
    assert not target.exists()
```

- [ ] **Step 11: Run the full suite to verify all cleanups land green**

```bash
cd apps/lab
.venv/bin/pytest -v
```

Expected: previous 71 + new tests all pass. Expected new count breakdown:
- test_util.py: 8 parametrized cases
- test_paths.py: +3 tests (find_project_id_from_pwd)
- test_cli_project.py: +4 tests (ls tag/label, set loe invalid, atomic new)
- test_cli_task.py: +4 tests (ls tag/label/due, set loe invalid)
- test_storage.py: +1 test (cleanup on failure)

Total: ~91 passing.

- [ ] **Step 12: Commit**

```bash
cd /Users/jcortes/src/productivity
git add apps/lab Makefile || true
git status
git commit -m "chore(lab): dedupe helpers, tighten id validation, atomic new, loe error wrap, missing filter tests"
```

---

## Task 2: `lab.index` module — Index dataclass + builder

**Files:**
- Create: `apps/lab/src/lab/index.py`
- Create: `apps/lab/tests/test_index.py`
- Modify: `apps/lab/src/lab/paths.py` (add `index_file()` helper)

- [ ] **Step 1: Add `index_file()` to `paths.py`**

APPEND to `paths.py`:

```python


def index_file(root: Path) -> Path:
    """Return the path of the global index cache (gitignored)."""
    return root / "knowledge" / ".index.json"
```

- [ ] **Step 2: Write failing tests for `build_index`**

Create `apps/lab/tests/test_index.py`:

```python
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from lab.index import Index, build_index, read_index, write_index


def test_build_index_empty_monorepo(monorepo: Path) -> None:
    idx = build_index(monorepo)
    assert idx["projects"] == []
    assert idx["tasks"] == []
    assert "generated_at" in idx


def test_build_index_counts_tasks_per_status(monorepo: Path, seed_project) -> None:
    pdir = seed_project("alpha")
    tasks = {
        "next_id": 5,
        "tasks": [
            {"id": 1, "title": "t1", "status": "todo", "priority": "P1",
             "loe": None, "due": None, "tags": [], "labels": [], "blocker": None,
             "notes_file": None, "created": "2026-04-16", "updated": "2026-04-16", "closed_at": None},
            {"id": 2, "title": "t2", "status": "in_progress", "priority": "P2",
             "loe": None, "due": "2026-04-20", "tags": ["x"], "labels": [], "blocker": None,
             "notes_file": None, "created": "2026-04-16", "updated": "2026-04-16", "closed_at": None},
            {"id": 3, "title": "t3", "status": "done", "priority": "P2",
             "loe": None, "due": None, "tags": [], "labels": [], "blocker": None,
             "notes_file": None, "created": "2026-04-16", "updated": "2026-04-16",
             "closed_at": "2026-04-16T12:00:00-07:00"},
            {"id": 4, "title": "t4", "status": "blocked", "priority": "P3",
             "loe": None, "due": None, "tags": [], "labels": [], "blocker": "x",
             "notes_file": None, "created": "2026-04-16", "updated": "2026-04-16", "closed_at": None},
        ],
    }
    (pdir / "tasks.json").write_text(json.dumps(tasks))

    idx = build_index(monorepo)
    assert len(idx["projects"]) == 1
    p = idx["projects"][0]
    assert p["id"] == "alpha"
    assert p["status"] == "active"
    assert p["open_task_count"] == 3  # todo + in_progress + blocked
    assert p["blocked_task_count"] == 1
    assert p["task_counts"] == {"todo": 1, "in_progress": 1, "blocked": 1, "done": 1}
    assert p["earliest_task_due"] == "2026-04-20"

    # tasks flattened across projects
    assert len(idx["tasks"]) == 4
    t2 = next(t for t in idx["tasks"] if t["task_id"] == 2)
    assert t2["project_id"] == "alpha"
    assert t2["title"] == "t2"
    assert t2["due"] == "2026-04-20"
    assert t2["path"] == "knowledge/projects/alpha/tasks.json#2"


def test_build_index_preserves_project_metadata(monorepo: Path, seed_project) -> None:
    pdir = seed_project("beta")
    data = json.loads((pdir / "project.json").read_text())
    data["tags"] = ["backend"]
    data["labels"] = ["lipy-davi"]
    data["priority"] = "P1"
    data["due"] = "2026-05-01"
    (pdir / "project.json").write_text(json.dumps(data))

    idx = build_index(monorepo)
    p = idx["projects"][0]
    assert p["tags"] == ["backend"]
    assert p["labels"] == ["lipy-davi"]
    assert p["priority"] == "P1"
    assert p["due"] == "2026-05-01"
    assert p["path"] == "knowledge/projects/beta"


def test_build_index_sorts_projects_by_id(monorepo: Path, seed_project) -> None:
    seed_project("zeta")
    seed_project("alpha")
    seed_project("mu")
    idx = build_index(monorepo)
    assert [p["id"] for p in idx["projects"]] == ["alpha", "mu", "zeta"]


def test_build_index_skips_non_project_dirs(monorepo: Path, seed_project) -> None:
    seed_project("alpha")
    # Create a directory that isn't a project (no project.json).
    (monorepo / "knowledge" / "projects" / "_scratch").mkdir()
    (monorepo / "knowledge" / "projects" / "_scratch" / "note.md").write_text("hi")

    idx = build_index(monorepo)
    assert [p["id"] for p in idx["projects"]] == ["alpha"]


def test_write_and_read_index_roundtrip(monorepo: Path, seed_project) -> None:
    seed_project("alpha")
    data = build_index(monorepo)
    path = write_index(monorepo, data)
    assert path == monorepo / "knowledge" / ".index.json"
    assert path.is_file()
    loaded = read_index(monorepo)
    assert loaded == data


def test_read_index_missing_raises(monorepo: Path) -> None:
    with pytest.raises(FileNotFoundError):
        read_index(monorepo)


def test_index_type_alias_is_dict() -> None:
    # Sanity: `Index` is a TypeAlias to a dict-like shape. Callers use plain dicts.
    # Ensures the module exposes the name.
    assert Index is not None
```

- [ ] **Step 3: Run — expect ImportError**

```bash
cd apps/lab
.venv/bin/pytest tests/test_index.py -v
```

Expected: collection error on `from lab.index import ...`.

- [ ] **Step 4: Implement `apps/lab/src/lab/index.py`**

```python
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lab import paths, storage


# Public type alias — the index is just a dict with a stable shape.
Index = dict[str, Any]


def _project_task_summary(tasks_doc: dict[str, Any]) -> dict[str, Any]:
    counts = {"todo": 0, "in_progress": 0, "blocked": 0, "done": 0}
    earliest_due: str | None = None
    for t in tasks_doc.get("tasks", []):
        s = t.get("status")
        if s in counts:
            counts[s] += 1
        due = t.get("due")
        if due and (earliest_due is None or due < earliest_due):
            earliest_due = due
    open_count = counts["todo"] + counts["in_progress"] + counts["blocked"]
    return {
        "task_counts": counts,
        "open_task_count": open_count,
        "blocked_task_count": counts["blocked"],
        "earliest_task_due": earliest_due,
    }


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).astimezone().isoformat(timespec="seconds")


def build_index(root: Path) -> Index:
    """Walk knowledge/projects/ and return the cached index shape.

    Projects are sorted by id. Tasks are emitted flat (one per row) with
    `project_id`, `task_id`, and path fields for cheap filtering.
    """
    projects_root = root / "knowledge" / "projects"
    project_rows: list[dict[str, Any]] = []
    task_rows: list[dict[str, Any]] = []

    if projects_root.is_dir():
        for child in sorted(projects_root.iterdir()):
            pjson = child / "project.json"
            tjson = child / "tasks.json"
            if not pjson.is_file():
                continue

            pdata = storage.read_json(pjson)
            tasks_doc = storage.read_json(tjson) if tjson.is_file() else {"tasks": []}
            summary = _project_task_summary(tasks_doc)

            project_rows.append({
                "id": pdata.get("id", child.name),
                "name": pdata.get("name", child.name),
                "description": pdata.get("description", ""),
                "status": pdata.get("status", "active"),
                "tags": list(pdata.get("tags") or []),
                "labels": list(pdata.get("labels") or []),
                "priority": pdata.get("priority"),
                "loe": pdata.get("loe"),
                "due": pdata.get("due"),
                "created": pdata.get("created"),
                "updated": pdata.get("updated"),
                "path": f"knowledge/projects/{child.name}",
                **summary,
            })

            for t in tasks_doc.get("tasks", []):
                task_rows.append({
                    "project_id": child.name,
                    "task_id": t["id"],
                    "title": t.get("title", ""),
                    "status": t.get("status"),
                    "priority": t.get("priority"),
                    "loe": t.get("loe"),
                    "due": t.get("due"),
                    "tags": list(t.get("tags") or []),
                    "labels": list(t.get("labels") or []),
                    "blocker": t.get("blocker"),
                    "notes_file": t.get("notes_file"),
                    "created": t.get("created"),
                    "updated": t.get("updated"),
                    "closed_at": t.get("closed_at"),
                    "path": f"knowledge/projects/{child.name}/tasks.json#{t['id']}",
                })

    return {
        "generated_at": _now_iso(),
        "projects": project_rows,
        "tasks": task_rows,
    }


def write_index(root: Path, data: Index) -> Path:
    """Persist `data` to `knowledge/.index.json`. Returns the written path."""
    path = paths.index_file(root)
    storage.write_json(path, data)
    return path


def read_index(root: Path) -> Index:
    """Load the cached index from disk. Raises FileNotFoundError if absent."""
    return storage.read_json(paths.index_file(root))
```

- [ ] **Step 5: Run — expect pass**

```bash
.venv/bin/pytest tests/test_index.py -v
```

Expected: 8 passed.

- [ ] **Step 6: Commit**

```bash
cd /Users/jcortes/src/productivity
git add apps/lab/src/lab/index.py apps/lab/src/lab/paths.py apps/lab/tests/test_index.py
git commit -m "feat(lab): index module with build/read/write helpers"
```

---

## Task 3: `lab index` CLI subgroup (rebuild + show)

**Files:**
- Create: `apps/lab/src/lab/commands/index.py`
- Modify: `apps/lab/src/lab/cli.py`
- Create: `apps/lab/tests/test_cli_index.py`

- [ ] **Step 1: Write failing tests**

Create `apps/lab/tests/test_cli_index.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from lab.cli import main


def test_index_rebuild_creates_file(monorepo: Path, seed_project) -> None:
    seed_project("alpha")
    runner = CliRunner()
    result = runner.invoke(main, ["index", "rebuild"])
    assert result.exit_code == 0, result.output

    index_path = monorepo / "knowledge" / ".index.json"
    assert index_path.is_file()
    idx = json.loads(index_path.read_text())
    assert len(idx["projects"]) == 1
    assert idx["projects"][0]["id"] == "alpha"


def test_index_rebuild_overwrites_stale(monorepo: Path, seed_project) -> None:
    seed_project("alpha")
    runner = CliRunner()
    runner.invoke(main, ["index", "rebuild"])
    seed_project("beta")
    runner.invoke(main, ["index", "rebuild"])

    idx = json.loads((monorepo / "knowledge" / ".index.json").read_text())
    assert {p["id"] for p in idx["projects"]} == {"alpha", "beta"}


def test_index_show_prints_json(monorepo: Path, seed_project) -> None:
    seed_project("alpha")
    runner = CliRunner()
    runner.invoke(main, ["index", "rebuild"])
    result = runner.invoke(main, ["index", "show"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert [p["id"] for p in parsed["projects"]] == ["alpha"]


def test_index_show_missing_rebuilds_implicitly(monorepo: Path, seed_project) -> None:
    seed_project("alpha")
    runner = CliRunner()
    result = runner.invoke(main, ["index", "show"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert [p["id"] for p in parsed["projects"]] == ["alpha"]
```

- [ ] **Step 2: Run — expect failures**

```bash
.venv/bin/pytest tests/test_cli_index.py -v
```

- [ ] **Step 3: Implement the subgroup**

Create `apps/lab/src/lab/commands/index.py`:

```python
from __future__ import annotations

import json as _json

import click

from lab import index as index_mod
from lab import paths


@click.group(name="index")
def index_group() -> None:
    """Global index (cache of projects + tasks) commands."""


@index_group.command("rebuild")
def rebuild() -> None:
    """Rebuild knowledge/.index.json from on-disk projects."""
    root = paths.find_monorepo_root()
    data = index_mod.build_index(root)
    path = index_mod.write_index(root, data)
    click.echo(f"wrote {path} ({len(data['projects'])} projects, {len(data['tasks'])} tasks)")


@index_group.command("show")
def show() -> None:
    """Print the cached index as JSON. Rebuilds implicitly if missing."""
    root = paths.find_monorepo_root()
    try:
        data = index_mod.read_index(root)
    except FileNotFoundError:
        data = index_mod.build_index(root)
        index_mod.write_index(root, data)
    click.echo(_json.dumps(data, indent=2))
```

- [ ] **Step 4: Register the subgroup in `cli.py`**

REPLACE `apps/lab/src/lab/cli.py`:

```python
from __future__ import annotations

import click

from lab.commands.index import index_group
from lab.commands.project import project_group
from lab.commands.task import task_group


@click.group()
@click.version_option(package_name="lab")
def main() -> None:
    """Unified CLI for the productivity monorepo."""


main.add_command(project_group)
main.add_command(task_group)
main.add_command(index_group)


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run — expect pass**

```bash
.venv/bin/pytest tests/test_cli_index.py -v
```

Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
cd /Users/jcortes/src/productivity
git add apps/lab/src/lab/cli.py apps/lab/src/lab/commands/index.py apps/lab/tests/test_cli_index.py
git commit -m "feat(lab): index subgroup (rebuild, show)"
```

---

## Task 4: Scaffold `apps/backend/` Python package

**Files:**
- Create: `apps/backend/pyproject.toml`
- Create: `apps/backend/README.md`
- Create: `apps/backend/backend` (shim)
- Create: `apps/backend/src/backend/__init__.py`
- Create: `apps/backend/src/backend/__main__.py`
- Create: `apps/backend/src/backend/config.py`
- Create: `apps/backend/src/backend/main.py`
- Create: `apps/backend/tests/__init__.py`
- Create: `apps/backend/tests/conftest.py`
- Create: `apps/backend/tests/test_health.py`
- Modify: `.gitignore`

- [ ] **Step 1: Create directory tree**

```bash
cd /Users/jcortes/src/productivity
mkdir -p apps/backend/src/backend/routes apps/backend/tests
```

- [ ] **Step 2: Write `apps/backend/pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "lab-backend"
version = "0.1.0"
description = "HTTP+WS backend for the productivity monorepo"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.109",
    "uvicorn[standard]>=0.27",
    "watchdog>=4.0",
    "lab",
]

[project.scripts]
lab-backend = "backend.main:run"

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-cov>=5.0",
    "httpx>=0.27",
]

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra --cov=backend --cov-report=term-missing"
```

- [ ] **Step 3: Write `apps/backend/README.md`**

```markdown
# lab-backend

FastAPI + watchdog backend for the productivity monorepo. Serves the cached global index, project/task reads, and markdown rendering over HTTP; broadcasts index-updated events over a WebSocket.

Design: `../../docs/superpowers/specs/2026-04-16-productivity-monorepo-design.md` §7.

## Dev

```
pip install -e .[dev]
pytest -v
```

## Run

```
make start       # from monorepo root
make stop
```

## Endpoints (Plan 2)

- `GET  /api/ping`
- `GET  /api/index`
- `GET  /api/projects[?status=...]`
- `GET  /api/projects/{id}`
- `GET  /api/projects/{id}/tasks`
- `GET  /api/projects/{id}/docs`
- `GET  /api/projects/{id}/file?path=...`
- `GET  /api/tasks[?status=...&priority=...&tag=...&label=...]`
- `GET  /api/tasks/due?days=N`
- `GET  /api/markdown?path=knowledge/...`
- `WS   /ws`
```

- [ ] **Step 4: Write shell shim `apps/backend/backend`**

```bash
#!/usr/bin/env bash
# Self-contained shim: resolve symlink so the installed /usr/local/bin/backend
# (or ~/.local/bin/backend) shim always uses the venv created by make install.
SOURCE="${BASH_SOURCE[0]}"
while [ -L "$SOURCE" ]; do
  DIR="$(cd "$(dirname "$SOURCE")" && pwd)"
  SOURCE="$(readlink "$SOURCE")"
  [[ $SOURCE != /* ]] && SOURCE="$DIR/$SOURCE"
done
SCRIPT_DIR="$(cd "$(dirname "$SOURCE")" && pwd)"
exec "$SCRIPT_DIR/.venv/bin/python" -m backend "$@"
```

Then:
```bash
chmod +x /Users/jcortes/src/productivity/apps/backend/backend
```

- [ ] **Step 5: Write the package stubs**

Create `apps/backend/src/backend/__init__.py`:
```python
__version__ = "0.1.0"
```

Create `apps/backend/src/backend/__main__.py`:
```python
from backend.main import run

if __name__ == "__main__":
    run()
```

Create `apps/backend/src/backend/config.py`:
```python
from __future__ import annotations

import os
from pathlib import Path

from lab import paths


def monorepo_root() -> Path:
    """Return the monorepo root used by all backend routes.

    Honors the same `LAB_ROOT` env var as the CLI — so tests can point the
    backend at a temp directory the same way.
    """
    return paths.find_monorepo_root()


def host() -> str:
    return os.environ.get("LAB_HOST", "0.0.0.0")


def port() -> int:
    return int(os.environ.get("LAB_PORT", "3333"))


DEBOUNCE_MS = int(os.environ.get("LAB_DEBOUNCE_MS", "250"))
```

Create `apps/backend/src/backend/main.py`:
```python
from __future__ import annotations

from fastapi import FastAPI

from backend import config


def create_app() -> FastAPI:
    """Application factory. Used by tests (TestClient) and the uvicorn entrypoint."""
    app = FastAPI(title="lab-backend", version="0.1.0")

    @app.get("/api/ping")
    async def ping() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()


def run() -> None:
    """Entrypoint for `python -m backend` and the `lab-backend` script."""
    import uvicorn

    uvicorn.run("backend.main:app", host=config.host(), port=config.port(), reload=False)
```

Create `apps/backend/tests/__init__.py`: (empty)

- [ ] **Step 6: Write `conftest.py` sharing lab fixtures**

Create `apps/backend/tests/conftest.py`:
```python
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def monorepo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Minimal monorepo for backend tests. Mirrors lab's fixture."""
    root = tmp_path / "productivity"
    (root / "knowledge" / "projects").mkdir(parents=True)
    (root / "knowledge" / "meetings").mkdir()
    (root / ".git").mkdir()
    monkeypatch.setenv("LAB_ROOT", str(root))
    monkeypatch.chdir(root)
    return root


@pytest.fixture()
def seed_project(monorepo: Path):
    def _create(project_id: str = "demo", *, description: str = "") -> Path:
        pdir = monorepo / "knowledge" / "projects" / project_id
        pdir.mkdir(parents=True)
        (pdir / "project.json").write_text(json.dumps({
            "id": project_id,
            "name": project_id,
            "description": description,
            "status": "active",
            "tags": [],
            "labels": [],
            "priority": None,
            "loe": None,
            "due": None,
            "created": "2026-04-17",
            "updated": "2026-04-17",
            "worktrees": [],
            "prs": [],
            "artifacts": [],
            "pinned": [],
        }, indent=2))
        (pdir / "tasks.json").write_text(json.dumps({"next_id": 1, "tasks": []}, indent=2))
        (pdir / "docs").mkdir()
        (pdir / "notes").mkdir()
        return pdir
    return _create


@pytest.fixture()
def client(monorepo: Path):
    """FastAPI TestClient pointed at the fixture monorepo."""
    from backend.main import create_app
    app = create_app()
    with TestClient(app) as c:
        yield c
```

- [ ] **Step 7: Write `test_health.py`**

Create `apps/backend/tests/test_health.py`:
```python
def test_ping(client) -> None:
    r = client.get("/api/ping")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
```

- [ ] **Step 8: Update root `.gitignore`**

APPEND to `/Users/jcortes/src/productivity/.gitignore`:
```
apps/backend/.venv/
apps/backend/.coverage
```

- [ ] **Step 9: Install backend into its own venv and smoke test**

```bash
cd /Users/jcortes/src/productivity/apps/backend
python3 -m venv .venv
.venv/bin/pip install -e '../lab' --quiet
.venv/bin/pip install -e '.[dev]' --quiet
.venv/bin/python -m backend --help 2>&1 || true  # uvicorn has no --help on main
.venv/bin/pytest -v
```

Expected: `test_ping` passes.

- [ ] **Step 10: Commit**

```bash
cd /Users/jcortes/src/productivity
git add apps/backend .gitignore
git status
git commit -m "feat(backend): scaffold FastAPI app with /api/ping smoke route"
```

---

## Task 5: `/api/index` route + shared `IndexCache`

**Files:**
- Create: `apps/backend/src/backend/state.py`
- Create: `apps/backend/src/backend/routes/__init__.py`
- Create: `apps/backend/src/backend/routes/index.py`
- Modify: `apps/backend/src/backend/main.py`
- Create: `apps/backend/tests/test_index_route.py`

- [ ] **Step 1: Write failing test**

Create `apps/backend/tests/test_index_route.py`:
```python
def test_get_index_empty(client) -> None:
    r = client.get("/api/index")
    assert r.status_code == 200
    body = r.json()
    assert body["projects"] == []
    assert body["tasks"] == []
    assert "generated_at" in body


def test_get_index_reflects_seeded_projects(client, seed_project) -> None:
    seed_project("alpha")
    seed_project("beta")
    r = client.get("/api/index")
    assert r.status_code == 200
    ids = [p["id"] for p in r.json()["projects"]]
    assert ids == ["alpha", "beta"]


def test_get_index_reflects_task_counts(client, seed_project) -> None:
    import json as _json
    pdir = seed_project("alpha")
    (pdir / "tasks.json").write_text(_json.dumps({
        "next_id": 3,
        "tasks": [
            {"id": 1, "title": "t", "status": "todo", "priority": "P1",
             "loe": None, "due": None, "tags": [], "labels": [], "blocker": None,
             "notes_file": None, "created": "2026-04-17", "updated": "2026-04-17", "closed_at": None},
            {"id": 2, "title": "u", "status": "done", "priority": "P1",
             "loe": None, "due": None, "tags": [], "labels": [], "blocker": None,
             "notes_file": None, "created": "2026-04-17", "updated": "2026-04-17",
             "closed_at": "2026-04-17T09:00:00-07:00"},
        ],
    }))
    r = client.get("/api/index")
    p = r.json()["projects"][0]
    assert p["open_task_count"] == 1
    assert p["task_counts"]["done"] == 1
```

- [ ] **Step 2: Run — expect 404**

```bash
cd apps/backend
.venv/bin/pytest tests/test_index_route.py -v
```

- [ ] **Step 3: Implement `backend/state.py`**

Create `apps/backend/src/backend/state.py`:
```python
from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from lab import index as index_mod


class IndexCache:
    """Thread-safe in-memory cache of the global index.

    On first access, builds from disk. On rebuild, regenerates from on-disk
    projects and persists to knowledge/.index.json.
    """

    def __init__(self, root: Path) -> None:
        self._root = root
        self._lock = threading.Lock()
        self._data: dict[str, Any] | None = None

    def rebuild(self) -> dict[str, Any]:
        with self._lock:
            data = index_mod.build_index(self._root)
            index_mod.write_index(self._root, data)
            self._data = data
            return data

    def get(self) -> dict[str, Any]:
        with self._lock:
            if self._data is not None:
                return self._data
        # Build outside the lock to avoid holding it during disk IO.
        return self.rebuild()
```

- [ ] **Step 4: Implement the route**

Create `apps/backend/src/backend/routes/__init__.py`: (empty)

Create `apps/backend/src/backend/routes/index.py`:
```python
from __future__ import annotations

from fastapi import APIRouter, Request


router = APIRouter()


@router.get("/api/index")
async def get_index(request: Request) -> dict:
    cache = request.app.state.index_cache
    return cache.get()
```

- [ ] **Step 5: Wire the router into `main.py`**

REPLACE `apps/backend/src/backend/main.py`:
```python
from __future__ import annotations

from fastapi import FastAPI

from backend import config
from backend.routes import index as index_route
from backend.state import IndexCache


def create_app() -> FastAPI:
    app = FastAPI(title="lab-backend", version="0.1.0")
    root = config.monorepo_root()
    app.state.index_cache = IndexCache(root)

    @app.get("/api/ping")
    async def ping() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(index_route.router)

    return app


app = create_app()


def run() -> None:
    import uvicorn

    uvicorn.run("backend.main:app", host=config.host(), port=config.port(), reload=False)
```

- [ ] **Step 6: Run — expect pass**

```bash
.venv/bin/pytest tests/test_index_route.py -v
```

Expected: 3 passed.

- [ ] **Step 7: Commit**

```bash
cd /Users/jcortes/src/productivity
git add apps/backend
git commit -m "feat(backend): /api/index route backed by thread-safe IndexCache"
```

---

## Task 6: `/api/projects` routes (list + single)

**Files:**
- Create: `apps/backend/src/backend/routes/project.py`
- Modify: `apps/backend/src/backend/main.py`
- Create: `apps/backend/tests/test_project_routes.py`

- [ ] **Step 1: Write failing tests**

Create `apps/backend/tests/test_project_routes.py`:
```python
import json


def test_list_projects_empty(client) -> None:
    r = client.get("/api/projects")
    assert r.status_code == 200
    assert r.json() == []


def test_list_projects_returns_index_slice(client, seed_project) -> None:
    seed_project("alpha")
    seed_project("beta")
    r = client.get("/api/projects")
    ids = [p["id"] for p in r.json()]
    assert ids == ["alpha", "beta"]


def test_list_projects_filter_by_status(client, seed_project, monorepo) -> None:
    alpha = seed_project("alpha")
    beta = seed_project("beta")
    data = json.loads((beta / "project.json").read_text())
    data["status"] = "archived"
    (beta / "project.json").write_text(json.dumps(data))
    # Refresh cache: a new seed changes the filesystem but the cache was built
    # on first /api/ping call in the fixture — tests must either rebuild
    # explicitly or rely on auto-build-on-first-read. We hit /api/index which
    # triggers a rebuild path if the cache is empty. For cache warmed by a
    # prior call, we'd need to rebuild. The IndexCache.get() only rebuilds
    # when the cache is empty, so the first route call on a fresh app primes
    # it. Since seed_project is called before any request, the index will be
    # correct on first read.
    r = client.get("/api/projects?status=active")
    ids = [p["id"] for p in r.json()]
    assert ids == ["alpha"]

    r = client.get("/api/projects?status=archived")
    ids = [p["id"] for p in r.json()]
    assert ids == ["beta"]


def test_get_single_project_returns_full_json(client, seed_project) -> None:
    seed_project("alpha", description="Alpha desc")
    r = client.get("/api/projects/alpha")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == "alpha"
    assert body["description"] == "Alpha desc"
    assert body["worktrees"] == []


def test_get_single_project_missing(client) -> None:
    r = client.get("/api/projects/nope")
    assert r.status_code == 404


def test_get_single_project_rejects_bad_id(client) -> None:
    r = client.get("/api/projects/..%2Fbad")
    assert r.status_code in {400, 404}
```

- [ ] **Step 2: Run — expect failures**

- [ ] **Step 3: Implement route**

Create `apps/backend/src/backend/routes/project.py`:
```python
from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from lab import paths, storage


router = APIRouter()

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9\-_]*$")


def _validate_project_id(project_id: str) -> None:
    if not _ID_RE.match(project_id):
        raise HTTPException(status_code=400, detail="invalid project id")


@router.get("/api/projects")
async def list_projects(request: Request, status: str | None = None,
                        tag: str | None = None, label: str | None = None) -> list[dict]:
    idx = request.app.state.index_cache.get()
    rows = idx["projects"]
    if status:
        rows = [r for r in rows if r.get("status") == status]
    if tag:
        rows = [r for r in rows if tag in (r.get("tags") or [])]
    if label:
        rows = [r for r in rows if label in (r.get("labels") or [])]
    return rows


@router.get("/api/projects/{project_id}")
async def get_project(project_id: str, request: Request) -> dict:
    _validate_project_id(project_id)
    root: Path = request.app.state.index_cache._root
    pjson = paths.project_file(root, project_id)
    if not pjson.is_file():
        raise HTTPException(status_code=404, detail=f"project {project_id!r} not found")
    return storage.read_json(pjson)
```

- [ ] **Step 4: Wire into `main.py`**

APPEND to `main.py` imports:
```python
from backend.routes import project as project_route
```

APPEND to `create_app()` (after `index_route` include):
```python
    app.include_router(project_route.router)
```

- [ ] **Step 5: Run — expect pass**

```bash
.venv/bin/pytest tests/test_project_routes.py -v
```

Expected: 6 passed.

- [ ] **Step 6: Commit**

```bash
cd /Users/jcortes/src/productivity
git add apps/backend
git commit -m "feat(backend): /api/projects list + single-project routes"
```

---

## Task 7: `/api/projects/{id}/tasks`

**Files:**
- Modify: `apps/backend/src/backend/routes/project.py`
- Modify: `apps/backend/tests/test_project_routes.py`

- [ ] **Step 1: Append failing tests**

APPEND to `test_project_routes.py`:
```python


def test_get_project_tasks_empty(client, seed_project) -> None:
    seed_project("alpha")
    r = client.get("/api/projects/alpha/tasks")
    assert r.status_code == 200
    assert r.json() == {"next_id": 1, "tasks": []}


def test_get_project_tasks_reflects_on_disk(client, seed_project) -> None:
    import json as _json
    pdir = seed_project("alpha")
    (pdir / "tasks.json").write_text(_json.dumps({
        "next_id": 2,
        "tasks": [{"id": 1, "title": "hi", "status": "todo", "priority": "P1",
                   "loe": None, "due": None, "tags": [], "labels": [],
                   "blocker": None, "notes_file": None,
                   "created": "2026-04-17", "updated": "2026-04-17", "closed_at": None}],
    }))
    r = client.get("/api/projects/alpha/tasks")
    body = r.json()
    assert body["next_id"] == 2
    assert body["tasks"][0]["title"] == "hi"


def test_get_project_tasks_missing_project(client) -> None:
    r = client.get("/api/projects/nope/tasks")
    assert r.status_code == 404
```

- [ ] **Step 2: Run — expect 404**

- [ ] **Step 3: Append route**

APPEND to `apps/backend/src/backend/routes/project.py`:
```python


@router.get("/api/projects/{project_id}/tasks")
async def get_project_tasks(project_id: str, request: Request) -> dict:
    _validate_project_id(project_id)
    root: Path = request.app.state.index_cache._root
    tjson = paths.tasks_file(root, project_id)
    if not tjson.is_file():
        raise HTTPException(status_code=404, detail=f"project {project_id!r} not found")
    return storage.read_json(tjson)
```

- [ ] **Step 4: Run — expect pass**

Expected: 9 passed in test_project_routes.py.

- [ ] **Step 5: Commit**

```bash
cd /Users/jcortes/src/productivity
git add apps/backend
git commit -m "feat(backend): /api/projects/{id}/tasks route"
```

---

## Task 8: `/api/tasks` + `/api/tasks/due`

**Files:**
- Create: `apps/backend/src/backend/routes/task.py`
- Modify: `apps/backend/src/backend/main.py`
- Create: `apps/backend/tests/test_task_routes.py`

- [ ] **Step 1: Write failing tests**

Create `apps/backend/tests/test_task_routes.py`:
```python
from __future__ import annotations

import json
from datetime import date, timedelta


def _task_entry(tid: int, **kwargs) -> dict:
    base = {
        "id": tid, "title": f"task-{tid}", "status": "todo", "priority": "P2",
        "loe": None, "due": None, "tags": [], "labels": [], "blocker": None,
        "notes_file": None, "created": "2026-04-17", "updated": "2026-04-17", "closed_at": None,
    }
    base.update(kwargs)
    return base


def _seed_tasks(pdir, tasks: list[dict]) -> None:
    (pdir / "tasks.json").write_text(json.dumps({"next_id": max(t["id"] for t in tasks) + 1,
                                                  "tasks": tasks}))


def test_list_tasks_empty(client) -> None:
    r = client.get("/api/tasks")
    assert r.status_code == 200
    assert r.json() == []


def test_list_tasks_flattens_across_projects(client, seed_project) -> None:
    a = seed_project("alpha")
    b = seed_project("beta")
    _seed_tasks(a, [_task_entry(1, title="in-alpha")])
    _seed_tasks(b, [_task_entry(1, title="in-beta")])
    r = client.get("/api/tasks")
    titles = [(t["project_id"], t["title"]) for t in r.json()]
    assert ("alpha", "in-alpha") in titles
    assert ("beta", "in-beta") in titles


def test_list_tasks_filter_by_status(client, seed_project) -> None:
    a = seed_project("alpha")
    _seed_tasks(a, [
        _task_entry(1, status="todo", title="t"),
        _task_entry(2, status="done", title="d", closed_at="2026-04-17T09:00:00-07:00"),
    ])
    r = client.get("/api/tasks?status=done")
    assert [t["title"] for t in r.json()] == ["d"]

    r = client.get("/api/tasks?status=open")
    assert [t["title"] for t in r.json()] == ["t"]


def test_list_tasks_filter_by_priority(client, seed_project) -> None:
    a = seed_project("alpha")
    _seed_tasks(a, [
        _task_entry(1, priority="P0"),
        _task_entry(2, priority="P1"),
        _task_entry(3, priority="P3"),
    ])
    r = client.get("/api/tasks?priority=P0,P1")
    assert {t["task_id"] for t in r.json()} == {1, 2}


def test_list_tasks_filter_by_tag_and_label(client, seed_project) -> None:
    a = seed_project("alpha")
    _seed_tasks(a, [
        _task_entry(1, tags=["review"]),
        _task_entry(2, labels=["lipy-davi"]),
        _task_entry(3),
    ])
    r = client.get("/api/tasks?tag=review")
    assert {t["task_id"] for t in r.json()} == {1}
    r = client.get("/api/tasks?label=lipy-davi")
    assert {t["task_id"] for t in r.json()} == {2}


def test_list_tasks_due(client, seed_project) -> None:
    a = seed_project("alpha")
    near = (date.today() + timedelta(days=3)).isoformat()
    far = (date.today() + timedelta(days=30)).isoformat()
    _seed_tasks(a, [
        _task_entry(1, due=near),
        _task_entry(2, due=far),
        _task_entry(3),  # no due
    ])
    r = client.get("/api/tasks/due?days=7")
    assert {t["task_id"] for t in r.json()} == {1}


def test_list_tasks_due_requires_positive_days(client) -> None:
    r = client.get("/api/tasks/due?days=0")
    assert r.status_code == 400
    r = client.get("/api/tasks/due?days=-1")
    assert r.status_code == 400
```

- [ ] **Step 2: Run — expect failures**

- [ ] **Step 3: Implement route**

Create `apps/backend/src/backend/routes/task.py`:
```python
from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, HTTPException, Query, Request


router = APIRouter()


@router.get("/api/tasks")
async def list_tasks(request: Request,
                     status: str | None = None,
                     priority: str | None = None,
                     tag: str | None = None,
                     label: str | None = None) -> list[dict]:
    idx = request.app.state.index_cache.get()
    rows = idx["tasks"]
    if status == "open":
        rows = [r for r in rows if r.get("status") != "done"]
    elif status:
        rows = [r for r in rows if r.get("status") == status]
    if priority:
        wanted = {p.strip() for p in priority.split(",") if p.strip()}
        rows = [r for r in rows if r.get("priority") in wanted]
    if tag:
        rows = [r for r in rows if tag in (r.get("tags") or [])]
    if label:
        rows = [r for r in rows if label in (r.get("labels") or [])]
    return rows


@router.get("/api/tasks/due")
async def list_tasks_due(request: Request, days: int = Query(..., ge=1)) -> list[dict]:
    if days < 1:
        raise HTTPException(status_code=400, detail="days must be positive")
    horizon = date.today() + timedelta(days=days)
    idx = request.app.state.index_cache.get()
    out: list[dict] = []
    for r in idx["tasks"]:
        due = r.get("due")
        if not due:
            continue
        if date.fromisoformat(due) <= horizon:
            out.append(r)
    return out
```

- [ ] **Step 4: Wire into `main.py`**

APPEND imports:
```python
from backend.routes import task as task_route
```

APPEND include (after project_route):
```python
    app.include_router(task_route.router)
```

- [ ] **Step 5: Run — expect pass**

Expected: 7 passed in test_task_routes.py.

- [ ] **Step 6: Commit**

```bash
cd /Users/jcortes/src/productivity
git add apps/backend
git commit -m "feat(backend): /api/tasks list + /api/tasks/due routes"
```

---

## Task 9: `/api/markdown` route

**Files:**
- Create: `apps/backend/src/backend/routes/markdown.py`
- Modify: `apps/backend/src/backend/main.py`
- Modify: `apps/backend/pyproject.toml` (add `markdown` and `pyyaml`)
- Create: `apps/backend/tests/test_markdown_route.py`

- [ ] **Step 1: Add deps**

MODIFY `apps/backend/pyproject.toml` `dependencies` section to include:
```toml
dependencies = [
    "fastapi>=0.109",
    "uvicorn[standard]>=0.27",
    "watchdog>=4.0",
    "markdown>=3.6",
    "pyyaml>=6.0",
    "lab",
]
```

Re-install:
```bash
cd apps/backend
.venv/bin/pip install -e '.[dev]' --quiet
```

- [ ] **Step 2: Write failing tests**

Create `apps/backend/tests/test_markdown_route.py`:
```python
def test_render_plain_markdown(client, monorepo) -> None:
    path = monorepo / "knowledge" / "meetings" / "hello.md"
    path.write_text("# Hello\n\nWorld")
    r = client.get("/api/markdown?path=knowledge/meetings/hello.md")
    assert r.status_code == 200
    body = r.json()
    assert "<h1>Hello</h1>" in body["html"]
    assert body["frontmatter"] == {}


def test_render_with_frontmatter(client, monorepo) -> None:
    path = monorepo / "knowledge" / "meetings" / "fm.md"
    path.write_text("---\ntitle: Test\ntags: [a, b]\n---\n\n# Body")
    r = client.get("/api/markdown?path=knowledge/meetings/fm.md")
    body = r.json()
    assert body["frontmatter"] == {"title": "Test", "tags": ["a", "b"]}
    assert "<h1>Body</h1>" in body["html"]


def test_render_missing_file(client) -> None:
    r = client.get("/api/markdown?path=knowledge/meetings/nope.md")
    assert r.status_code == 404


def test_render_rejects_traversal(client) -> None:
    r = client.get("/api/markdown?path=../etc/passwd")
    assert r.status_code == 400
    r = client.get("/api/markdown?path=/etc/passwd")
    assert r.status_code == 400


def test_render_rejects_non_markdown(client, monorepo) -> None:
    path = monorepo / "knowledge" / "meetings" / "hello.txt"
    path.write_text("hi")
    r = client.get("/api/markdown?path=knowledge/meetings/hello.txt")
    assert r.status_code == 400
```

- [ ] **Step 3: Run — expect failures**

- [ ] **Step 4: Implement route**

Create `apps/backend/src/backend/routes/markdown.py`:
```python
from __future__ import annotations

import re
from pathlib import Path

import markdown as _md
import yaml
from fastapi import APIRouter, HTTPException, Request


router = APIRouter()

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.+?)\n---\s*\n", re.DOTALL)

_RENDERER = _md.Markdown(
    extensions=["fenced_code", "codehilite", "tables", "toc", "nl2br", "sane_lists"],
    extension_configs={"codehilite": {"css_class": "highlight", "guess_lang": False}},
)


def _safe_resolve(root: Path, rel: str) -> Path:
    if rel.startswith("/"):
        raise HTTPException(status_code=400, detail="absolute paths not allowed")
    if ".." in Path(rel).parts:
        raise HTTPException(status_code=400, detail="path traversal not allowed")
    if not rel.lower().endswith(".md"):
        raise HTTPException(status_code=400, detail="only .md files supported")
    target = (root / rel).resolve()
    # Ensure target is still inside root (defense-in-depth).
    if root.resolve() not in target.parents and target != root.resolve():
        raise HTTPException(status_code=400, detail="path escapes monorepo")
    return target


@router.get("/api/markdown")
async def render_markdown(path: str, request: Request) -> dict:
    root: Path = request.app.state.index_cache._root
    target = _safe_resolve(root, path)
    if not target.is_file():
        raise HTTPException(status_code=404, detail="not found")

    text = target.read_text(encoding="utf-8")
    frontmatter: dict = {}
    body = text
    m = _FRONTMATTER_RE.match(text)
    if m:
        try:
            frontmatter = yaml.safe_load(m.group(1)) or {}
        except yaml.YAMLError:
            frontmatter = {}
        body = text[m.end():]

    _RENDERER.reset()
    html = _RENDERER.convert(body)
    return {"frontmatter": frontmatter, "html": html}
```

- [ ] **Step 5: Wire into `main.py`**

APPEND imports:
```python
from backend.routes import markdown as markdown_route
```

APPEND include:
```python
    app.include_router(markdown_route.router)
```

- [ ] **Step 6: Run — expect pass**

Expected: 5 passed.

- [ ] **Step 7: Commit**

```bash
cd /Users/jcortes/src/productivity
git add apps/backend
git commit -m "feat(backend): /api/markdown route with frontmatter parsing"
```

---

## Task 10: `/api/projects/{id}/docs` and `/api/projects/{id}/file`

**Files:**
- Modify: `apps/backend/src/backend/routes/project.py`
- Modify: `apps/backend/tests/test_project_routes.py`

- [ ] **Step 1: Append failing tests**

APPEND to `test_project_routes.py`:
```python


def test_list_project_docs(client, seed_project) -> None:
    pdir = seed_project("alpha")
    (pdir / "docs" / "one-pager.md").write_text("# hello")
    (pdir / "notes" / "001-draft.md").write_text("# draft")
    (pdir / "assets" / "chart.png").write_bytes(b"\x89PNG")

    r = client.get("/api/projects/alpha/docs")
    assert r.status_code == 200
    files = r.json()
    paths_set = {f["path"] for f in files}
    assert "docs/one-pager.md" in paths_set
    assert "notes/001-draft.md" in paths_set
    assert "assets/chart.png" in paths_set


def test_list_project_docs_missing_project(client) -> None:
    r = client.get("/api/projects/nope/docs")
    assert r.status_code == 404


def test_get_project_file_text(client, seed_project) -> None:
    pdir = seed_project("alpha")
    (pdir / "docs" / "one-pager.md").write_text("# body")
    r = client.get("/api/projects/alpha/file?path=docs/one-pager.md")
    assert r.status_code == 200
    assert "# body" in r.text


def test_get_project_file_rejects_traversal(client, seed_project) -> None:
    seed_project("alpha")
    r = client.get("/api/projects/alpha/file?path=../beta.md")
    assert r.status_code == 400


def test_get_project_file_missing(client, seed_project) -> None:
    seed_project("alpha")
    r = client.get("/api/projects/alpha/file?path=notes/999.md")
    assert r.status_code == 404
```

- [ ] **Step 2: Run — expect failures**

- [ ] **Step 3: Append routes**

APPEND to `apps/backend/src/backend/routes/project.py`:
```python
from fastapi.responses import FileResponse


@router.get("/api/projects/{project_id}/docs")
async def list_project_docs(project_id: str, request: Request) -> list[dict]:
    _validate_project_id(project_id)
    root: Path = request.app.state.index_cache._root
    pdir = paths.project_dir(root, project_id)
    if not pdir.is_dir():
        raise HTTPException(status_code=404, detail=f"project {project_id!r} not found")

    out: list[dict] = []
    for sub in ("docs", "notes", "assets"):
        sub_dir = pdir / sub
        if not sub_dir.is_dir():
            continue
        for f in sorted(sub_dir.rglob("*")):
            if f.is_file():
                out.append({
                    "path": str(f.relative_to(pdir)),
                    "size": f.stat().st_size,
                })
    return out


@router.get("/api/projects/{project_id}/file")
async def get_project_file(project_id: str, path: str, request: Request):
    _validate_project_id(project_id)
    if path.startswith("/") or ".." in Path(path).parts:
        raise HTTPException(status_code=400, detail="invalid path")
    root: Path = request.app.state.index_cache._root
    pdir = paths.project_dir(root, project_id)
    target = (pdir / path).resolve()
    if pdir.resolve() not in target.parents and target != pdir.resolve():
        raise HTTPException(status_code=400, detail="path escapes project")
    if not target.is_file():
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(target)
```

- [ ] **Step 4: Run — expect pass**

Expected: 14 passed in test_project_routes.py (9 prior + 5 new).

- [ ] **Step 5: Commit**

```bash
cd /Users/jcortes/src/productivity
git add apps/backend
git commit -m "feat(backend): /api/projects/{id}/docs and /file raw routes with traversal guard"
```

---

## Task 11: Watcher module with debounce

**Files:**
- Create: `apps/backend/src/backend/watcher.py`
- Create: `apps/backend/tests/test_watcher.py`

- [ ] **Step 1: Write failing tests**

Create `apps/backend/tests/test_watcher.py`:
```python
from __future__ import annotations

import time
from pathlib import Path

from backend.state import IndexCache
from backend.watcher import IndexWatcher


def test_watcher_debounces_bursts(monorepo: Path) -> None:
    """Rapid successive changes should trigger exactly one rebuild."""
    cache = IndexCache(monorepo)
    cache.rebuild()
    rebuild_count = {"n": 0}

    def on_rebuild(_data) -> None:
        rebuild_count["n"] += 1

    w = IndexWatcher(monorepo, cache, debounce_ms=100, on_rebuild=on_rebuild)
    w.start()
    try:
        target = monorepo / "knowledge" / "projects" / ".probe"
        target.mkdir()
        for i in range(5):
            (target / f"f{i}.md").write_text("x")
            time.sleep(0.01)
        time.sleep(0.3)  # give debouncer time to fire
    finally:
        w.stop()

    assert rebuild_count["n"] == 1


def test_watcher_rebuilds_on_project_creation(monorepo: Path, seed_project) -> None:
    cache = IndexCache(monorepo)
    cache.rebuild()
    events: list[dict] = []

    def on_rebuild(data) -> None:
        events.append(data)

    w = IndexWatcher(monorepo, cache, debounce_ms=100, on_rebuild=on_rebuild)
    w.start()
    try:
        seed_project("late-comer")
        time.sleep(0.3)
    finally:
        w.stop()

    assert len(events) == 1
    ids = [p["id"] for p in events[0]["projects"]]
    assert "late-comer" in ids


def test_watcher_stop_is_idempotent(monorepo: Path) -> None:
    cache = IndexCache(monorepo)
    w = IndexWatcher(monorepo, cache, debounce_ms=100, on_rebuild=lambda d: None)
    w.start()
    w.stop()
    w.stop()  # should not raise
```

- [ ] **Step 2: Run — expect ImportError**

- [ ] **Step 3: Implement the watcher**

Create `apps/backend/src/backend/watcher.py`:
```python
from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Callable

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from backend.state import IndexCache


class IndexWatcher:
    """Watch `knowledge/` and rebuild the index on any change, debounced."""

    def __init__(self, root: Path, cache: IndexCache, *,
                 debounce_ms: int,
                 on_rebuild: Callable[[dict[str, Any]], None]) -> None:
        self._root = root
        self._cache = cache
        self._debounce_s = debounce_ms / 1000.0
        self._on_rebuild = on_rebuild
        self._observer: Observer | None = None
        self._timer: threading.Timer | None = None
        self._timer_lock = threading.Lock()
        self._stopped = False

    def _on_change(self, _event: FileSystemEvent) -> None:
        with self._timer_lock:
            if self._stopped:
                return
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(self._debounce_s, self._fire)
            self._timer.daemon = True
            self._timer.start()

    def _fire(self) -> None:
        if self._stopped:
            return
        data = self._cache.rebuild()
        try:
            self._on_rebuild(data)
        except Exception:
            # Broadcast failures must not crash the watcher thread.
            pass

    def start(self) -> None:
        handler = FileSystemEventHandler()
        handler.on_any_event = self._on_change
        observer = Observer()
        knowledge = self._root / "knowledge"
        knowledge.mkdir(parents=True, exist_ok=True)
        observer.schedule(handler, str(knowledge), recursive=True)
        observer.start()
        self._observer = observer

    def stop(self) -> None:
        with self._timer_lock:
            self._stopped = True
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=2.0)
            self._observer = None
```

- [ ] **Step 4: Run — expect pass**

```bash
.venv/bin/pytest tests/test_watcher.py -v
```

Expected: 3 passed. (May take ~1 second due to sleeps.)

- [ ] **Step 5: Commit**

```bash
cd /Users/jcortes/src/productivity
git add apps/backend
git commit -m "feat(backend): IndexWatcher with debounced filesystem observer"
```

---

## Task 12: WebSocket `/ws` + broadcaster

**Files:**
- Modify: `apps/backend/src/backend/state.py` (add `WsBroadcaster`)
- Create: `apps/backend/src/backend/routes/ws.py`
- Modify: `apps/backend/src/backend/main.py`
- Create: `apps/backend/tests/test_ws.py`

- [ ] **Step 1: Write failing tests**

Create `apps/backend/tests/test_ws.py`:
```python
def test_ws_connects_and_closes(client) -> None:
    with client.websocket_connect("/ws") as ws:
        # No messages until something triggers a broadcast; keep idle.
        pass


def test_ws_receives_index_updated_after_broadcast(client) -> None:
    with client.websocket_connect("/ws") as ws:
        # Trigger a broadcast manually via app.state.ws_broadcaster.
        from backend.state import IndexUpdatedEvent
        app = client.app
        import asyncio
        asyncio.run(app.state.ws_broadcaster.publish(IndexUpdatedEvent(ts="2026-04-17T12:00:00-07:00")))
        data = ws.receive_json()
        assert data == {"type": "index-updated", "ts": "2026-04-17T12:00:00-07:00"}
```

- [ ] **Step 2: Run — expect ImportError**

- [ ] **Step 3: Extend `state.py`**

APPEND to `apps/backend/src/backend/state.py`:
```python
import asyncio
from dataclasses import dataclass


@dataclass
class IndexUpdatedEvent:
    ts: str

    def to_json(self) -> dict:
        return {"type": "index-updated", "ts": self.ts}


class WsBroadcaster:
    """In-memory list of connected WebSockets with an async publish fan-out."""

    def __init__(self) -> None:
        self._clients: list = []
        self._lock = asyncio.Lock()

    async def add(self, websocket) -> None:
        async with self._lock:
            self._clients.append(websocket)

    async def remove(self, websocket) -> None:
        async with self._lock:
            if websocket in self._clients:
                self._clients.remove(websocket)

    async def publish(self, event: IndexUpdatedEvent) -> None:
        async with self._lock:
            clients = list(self._clients)
        for ws in clients:
            try:
                await ws.send_json(event.to_json())
            except Exception:
                # Drop broken sockets on next remove.
                pass
```

- [ ] **Step 4: Create the WS route**

Create `apps/backend/src/backend/routes/ws.py`:
```python
from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect


router = APIRouter()


@router.websocket("/ws")
async def ws_endpoint(websocket: WebSocket) -> None:
    broadcaster = websocket.app.state.ws_broadcaster
    await websocket.accept()
    await broadcaster.add(websocket)
    try:
        while True:
            # Server doesn't expect client messages for Plan 2; drain anything
            # the client sends to keep the socket alive.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await broadcaster.remove(websocket)
```

- [ ] **Step 5: Wire into `main.py` + instantiate broadcaster**

REPLACE `apps/backend/src/backend/main.py`:
```python
from __future__ import annotations

from fastapi import FastAPI

from backend import config
from backend.routes import index as index_route
from backend.routes import markdown as markdown_route
from backend.routes import project as project_route
from backend.routes import task as task_route
from backend.routes import ws as ws_route
from backend.state import IndexCache, WsBroadcaster


def create_app() -> FastAPI:
    app = FastAPI(title="lab-backend", version="0.1.0")
    root = config.monorepo_root()
    app.state.index_cache = IndexCache(root)
    app.state.ws_broadcaster = WsBroadcaster()

    @app.get("/api/ping")
    async def ping() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(index_route.router)
    app.include_router(project_route.router)
    app.include_router(task_route.router)
    app.include_router(markdown_route.router)
    app.include_router(ws_route.router)

    return app


app = create_app()


def run() -> None:
    import uvicorn

    uvicorn.run("backend.main:app", host=config.host(), port=config.port(), reload=False)
```

- [ ] **Step 6: Run — expect pass**

Expected: 2 passed in test_ws.py.

- [ ] **Step 7: Commit**

```bash
cd /Users/jcortes/src/productivity
git add apps/backend
git commit -m "feat(backend): WebSocket /ws with WsBroadcaster fan-out"
```

---

## Task 13: Integrate watcher into backend lifespan

**Files:**
- Modify: `apps/backend/src/backend/main.py`
- Create: `apps/backend/tests/test_integration_e2e.py`

- [ ] **Step 1: Add lifespan wiring**

REPLACE the `create_app()` function in `main.py`:
```python
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI

from backend import config
from backend.routes import index as index_route
from backend.routes import markdown as markdown_route
from backend.routes import project as project_route
from backend.routes import task as task_route
from backend.routes import ws as ws_route
from backend.state import IndexCache, IndexUpdatedEvent, WsBroadcaster
from backend.watcher import IndexWatcher


@asynccontextmanager
async def lifespan(app: FastAPI):
    root = config.monorepo_root()
    cache = IndexCache(root)
    broadcaster = WsBroadcaster()

    cache.rebuild()  # prime disk + memory

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

    @app.get("/api/ping")
    async def ping() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(index_route.router)
    app.include_router(project_route.router)
    app.include_router(task_route.router)
    app.include_router(markdown_route.router)
    app.include_router(ws_route.router)

    return app


app = create_app()


def run() -> None:
    import uvicorn

    uvicorn.run("backend.main:app", host=config.host(), port=config.port(), reload=False)
```

- [ ] **Step 2: Write the end-to-end integration test**

Create `apps/backend/tests/test_integration_e2e.py`:
```python
from __future__ import annotations

import json
import time
from pathlib import Path

from fastapi.testclient import TestClient


def test_cli_write_propagates_through_watcher_to_ws(monorepo: Path, seed_project) -> None:
    """Full loop: create project → fs event → watcher rebuild → WS broadcast."""
    from backend.main import create_app

    app = create_app()
    with TestClient(app) as client:
        # Index starts empty
        r = client.get("/api/index")
        assert r.json()["projects"] == []

        with client.websocket_connect("/ws") as ws:
            # Simulate "lab project new" by creating the project.json directly.
            seed_project("alpha")
            # Wait for debounce + rebuild
            time.sleep(0.5)
            msg = ws.receive_json()
            assert msg["type"] == "index-updated"

        # Index reflects the change
        r = client.get("/api/index")
        ids = [p["id"] for p in r.json()["projects"]]
        assert ids == ["alpha"]
```

- [ ] **Step 3: Run — expect pass**

```bash
cd apps/backend
.venv/bin/pytest -v
```

Expected: all tests pass including the new integration test.

- [ ] **Step 4: Commit**

```bash
cd /Users/jcortes/src/productivity
git add apps/backend
git commit -m "feat(backend): integrate watcher into lifespan; end-to-end WS propagation test"
```

---

## Task 14: `make start`, `make stop`, `make start-bg` + `lab start`/`stop`/`open`

**Files:**
- Modify: `Makefile`
- Create: `apps/lab/src/lab/commands/service.py`
- Modify: `apps/lab/src/lab/cli.py`
- Create: `apps/lab/tests/test_cli_service.py`

- [ ] **Step 1: Replace the `Makefile`**

REPLACE `/Users/jcortes/src/productivity/Makefile`:
```makefile
.PHONY: install uninstall test start stop start-bg

LAB_VENV := apps/lab/.venv
BACKEND_VENV := apps/backend/.venv
BIN_DIR := $(HOME)/.local/bin
PID_FILE := .lab-backend.pid

install:
	@mkdir -p $(BIN_DIR)
	@test -d $(LAB_VENV) || python3 -m venv $(LAB_VENV)
	@$(LAB_VENV)/bin/pip install -e 'apps/lab[dev]' --quiet
	@ln -sf $(CURDIR)/apps/lab/lab $(BIN_DIR)/lab
	@test -d $(BACKEND_VENV) || python3 -m venv $(BACKEND_VENV)
	@$(BACKEND_VENV)/bin/pip install -e 'apps/lab' --quiet
	@$(BACKEND_VENV)/bin/pip install -e 'apps/backend[dev]' --quiet
	@ln -sf $(CURDIR)/apps/backend/backend $(BIN_DIR)/lab-backend
	@echo "Installed lab → $(BIN_DIR)/lab"
	@echo "Installed lab-backend → $(BIN_DIR)/lab-backend"
	@echo "Ensure $(BIN_DIR) is on your PATH."

uninstall:
	@rm -f $(BIN_DIR)/lab $(BIN_DIR)/lab-backend
	@rm -rf $(LAB_VENV) $(BACKEND_VENV)
	@echo "Uninstalled."

test:
	@$(LAB_VENV)/bin/pytest apps/lab/tests -v
	@$(BACKEND_VENV)/bin/pytest apps/backend/tests -v

start:
	@$(BACKEND_VENV)/bin/python -m backend

start-bg:
	@if [ -f $(PID_FILE) ] && kill -0 $$(cat $(PID_FILE)) 2>/dev/null; then \
		echo "backend already running (pid $$(cat $(PID_FILE)))"; \
	else \
		nohup $(BACKEND_VENV)/bin/python -m backend > .lab-backend.log 2>&1 & \
		echo $$! > $(PID_FILE); \
		echo "started backend (pid $$(cat $(PID_FILE))); logs in .lab-backend.log"; \
	fi

stop:
	@if [ -f $(PID_FILE) ]; then \
		pid=$$(cat $(PID_FILE)); \
		kill $$pid 2>/dev/null && echo "stopped backend (pid $$pid)" || echo "no running backend (stale pid $$pid)"; \
		rm -f $(PID_FILE); \
	else \
		echo "no pid file ($(PID_FILE))"; \
	fi
```

APPEND to `.gitignore`:
```
.lab-backend.pid
.lab-backend.log
```

- [ ] **Step 2: Write failing tests for `lab start/stop/open` wrappers**

Create `apps/lab/tests/test_cli_service.py`:
```python
from __future__ import annotations

from click.testing import CliRunner

from lab.cli import main


def test_start_invokes_make(monkeypatch) -> None:
    called: list[list[str]] = []

    def fake_run(cmd, check, cwd=None):
        called.append(cmd)
        class R:
            returncode = 0
        return R()

    monkeypatch.setattr("lab.commands.service.subprocess.run", fake_run)
    result = CliRunner().invoke(main, ["start"])
    assert result.exit_code == 0, result.output
    assert called and called[0][:2] == ["make", "start-bg"]


def test_stop_invokes_make(monkeypatch) -> None:
    called: list[list[str]] = []

    def fake_run(cmd, check, cwd=None):
        called.append(cmd)
        class R:
            returncode = 0
        return R()

    monkeypatch.setattr("lab.commands.service.subprocess.run", fake_run)
    result = CliRunner().invoke(main, ["stop"])
    assert result.exit_code == 0
    assert called and called[0][:2] == ["make", "stop"]


def test_open_calls_webbrowser(monkeypatch) -> None:
    opened: list[str] = []
    monkeypatch.setattr("lab.commands.service.webbrowser.open", lambda u: opened.append(u))
    result = CliRunner().invoke(main, ["open"])
    assert result.exit_code == 0
    assert opened == ["http://localhost:3333/api/index"]
```

- [ ] **Step 3: Run — expect failures**

- [ ] **Step 4: Implement the wrappers**

Create `apps/lab/src/lab/commands/service.py`:
```python
from __future__ import annotations

import subprocess
import webbrowser

import click

from lab import paths


@click.command(name="start")
def start() -> None:
    """Start the backend in the background (`make start-bg`)."""
    root = paths.find_monorepo_root()
    subprocess.run(["make", "start-bg"], check=True, cwd=str(root))


@click.command(name="stop")
def stop() -> None:
    """Stop the running backend (`make stop`)."""
    root = paths.find_monorepo_root()
    subprocess.run(["make", "stop"], check=True, cwd=str(root))


@click.command(name="open")
def open_cmd() -> None:
    """Open the backend index URL in the default browser."""
    webbrowser.open("http://localhost:3333/api/index")
```

- [ ] **Step 5: Register in `cli.py`**

REPLACE `apps/lab/src/lab/cli.py`:
```python
from __future__ import annotations

import click

from lab.commands.index import index_group
from lab.commands.project import project_group
from lab.commands.service import open_cmd, start, stop
from lab.commands.task import task_group


@click.group()
@click.version_option(package_name="lab")
def main() -> None:
    """Unified CLI for the productivity monorepo."""


main.add_command(project_group)
main.add_command(task_group)
main.add_command(index_group)
main.add_command(start)
main.add_command(stop)
main.add_command(open_cmd)


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Run tests**

```bash
cd apps/lab
.venv/bin/pytest tests/test_cli_service.py -v
```

Expected: 3 passed.

- [ ] **Step 7: Commit**

```bash
cd /Users/jcortes/src/productivity
git add Makefile .gitignore apps/lab
git commit -m "feat: make start/stop/start-bg targets and lab start/stop/open wrappers"
```

---

## Task 15: Final live smoke test + wrap-up

No new files — this task verifies everything works end-to-end with the actual backend process (not just TestClient).

- [ ] **Step 1: Run `make install` to (re)wire both venvs**

```bash
cd /Users/jcortes/src/productivity
make install
```

Expected output mentions both `lab` and `lab-backend` symlinks.

- [ ] **Step 2: Run full test suite via `make test`**

```bash
make test
```

Expected: lab suite passes (~91 tests), backend suite passes (~30+ tests across routes, watcher, ws, integration).

- [ ] **Step 3: Start backend in background and verify API**

```bash
make start-bg
sleep 2
curl -sf http://localhost:3333/api/ping | tee /dev/stderr | grep -q '"status":"ok"'
curl -sf http://localhost:3333/api/index | python3 -c 'import sys, json; d = json.load(sys.stdin); print("projects:", len(d["projects"]), "tasks:", len(d["tasks"]))'
```

Expected: ping returns 200 with ok; index returns the currently-populated shape (may be 0 projects if running against a fresh monorepo).

- [ ] **Step 4: Verify watcher responds to a real CLI mutation**

```bash
cd /Users/jcortes/src/productivity
LAB_ROOT=$HOME/src/productivity ~/.local/bin/lab project new smoke-test --desc "Plan 2 smoke" || \
  echo "(pre-existing project — fine; delete it first if you want a fresh test)"
sleep 1
curl -sf http://localhost:3333/api/index | python3 -c 'import sys, json; d = json.load(sys.stdin); ids = [p["id"] for p in d["projects"]]; print(ids); assert "smoke-test" in ids'
```

Expected: the list includes `smoke-test` — proving the watcher picked up the new project.json.

- [ ] **Step 5: Stop the backend**

```bash
make stop
```

Expected: `stopped backend (pid …)`.

- [ ] **Step 6: Clean up the smoke-test project**

```bash
~/.local/bin/lab project rm smoke-test --yes
```

- [ ] **Step 7: (Optional) Commit any incidental fixes found during smoke test**

```bash
git status
# If anything unexpected was modified, commit with a descriptive message.
```

---

## Plan 2 — Done when

1. `lab index rebuild` writes `knowledge/.index.json` correctly.
2. `make start` (and `make start-bg`) boot a FastAPI backend on `:3333`.
3. All `/api/*` routes listed in the goals section return sensible JSON.
4. WebSocket `/ws` broadcasts `{"type":"index-updated", "ts":<iso>}` on filesystem changes under `knowledge/`.
5. Watcher debounces bursts to a single rebuild.
6. `make test` runs both `apps/lab/tests/` and `apps/backend/tests/` and both pass.
7. Plan-1 tech debt items (dedup helpers, id validation, atomic new, loe wrap, missing filter tests) are closed.
8. Commit log tells a clean per-task story.

## What's NOT in Plan 2 (pointer list)

| Feature | Plan |
|---|---|
| HTML/JS frontend — dashboard, project view, timeline, list views | Plan 3 |
| POST/PUT/DELETE API endpoints | Plan 3 (or later) |
| `lab project add` / `lab project remove` — worktree commands + MP prefix config | Plan 4 |
| `lab search` — full-text across projects/tasks/docs | Plan 5 |
| `lab pr add`, `lab artifact add`, `lab note` | Plan 5 |
| Migration agent + `lab migrate` | Plan 6 |
| Moving `apps/darwin-runner`, `apps/darwin-backups`, `apps/trustim-ir-cli` | Plan 7 |
| Diff routes + notebook handling | Plan 8 (gdiff/mdview merge) |

Plan 2 is self-contained: by the end, the backend serves the full read surface a future frontend needs. Plan 3 can start immediately with nothing more than HTTP + a WebSocket client.
