"""Read-only API for the client-owned global Assistant task database."""
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from lab import assistant as assistant_db
from lab import paths

from core import auth


router = APIRouter(prefix="/api/assistant")


def _root() -> Path | None:
    return paths.assistant_root()


def _require_root(request: Request) -> Path:
    auth.require_admin(request)
    root = _root()
    if root is None:
        raise HTTPException(
            status_code=503,
            detail="Assistant database is not configured; set LAB_ASSISTANT_HOME in the Lab client .env",
        )
    if not root.is_dir():
        raise HTTPException(
            status_code=503,
            detail=f"Assistant database directory does not exist: {root}",
        )
    return root


def _summary(body: str, limit: int = 180) -> str:
    parts: list[str] = []
    for raw in body.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("```"):
            continue
        line = line.removeprefix("- [ ] ").removeprefix("- [x] ").removeprefix("- ")
        parts.append(line)
        if len(" ".join(parts)) >= limit:
            break
    text = " ".join(parts)
    return text[:limit].rstrip() + ("…" if len(text) > limit else "")


def _task_sort_key(task: dict) -> tuple:
    status_order = {
        "in_progress": 0,
        "ready": 1,
        "inbox": 2,
        "blocked": 3,
        "waiting": 4,
        "done": 5,
    }
    priority_order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    return (
        status_order.get(str(task.get("status")), 99),
        priority_order.get(str(task.get("priority")), 99),
        -float(task.get("mtime") or 0),
    )


@router.get("")
def get_assistant(request: Request) -> dict:
    auth.require_admin(request)
    root = _root()
    if root is None:
        return {
            "configured": False,
            "exists": False,
            "root": None,
            "projects": [],
            "tasks": [],
            "statuses": list(assistant_db.STATUSES),
            "priorities": list(assistant_db.PRIORITIES),
        }
    if not root.is_dir():
        return {
            "configured": True,
            "exists": False,
            "root": str(root),
            "projects": [],
            "tasks": [],
            "statuses": list(assistant_db.STATUSES),
            "priorities": list(assistant_db.PRIORITIES),
        }

    projects = list(assistant_db.iter_projects(root))
    tasks = []
    for task in assistant_db.iter_tasks(root, projects):
        row = dict(task)
        body = str(row.pop("body", ""))
        row["summary"] = _summary(body)
        tasks.append(row)
    tasks.sort(key=_task_sort_key)
    return {
        "configured": True,
        "exists": True,
        "initialized": (root / "AGENTS.md").is_file(),
        "root": str(root),
        "projects": projects,
        "tasks": tasks,
        "statuses": list(assistant_db.STATUSES),
        "priorities": list(assistant_db.PRIORITIES),
    }


def _safe_task_path(root: Path, relative: str) -> Path:
    rel = Path(relative)
    if rel.is_absolute() or ".." in rel.parts or rel.suffix.lower() != ".md":
        raise HTTPException(status_code=400, detail="invalid task path")
    target = (root / rel).resolve()
    if root.resolve() not in target.parents:
        raise HTTPException(status_code=400, detail="task path escapes Assistant database")
    if not target.is_file():
        raise HTTPException(status_code=404, detail="task not found")
    return target


@router.get("/task")
def get_task(path: str, request: Request) -> dict:
    root = _require_root(request)
    source = _safe_task_path(root, path)
    metadata, body = assistant_db.read_markdown(source)
    project_id = str(metadata.get("project") or source.parent.parent.name)
    project_source = root / "projects" / project_id / "project.md"
    project: dict = {}
    if project_source.is_file():
        project, _ = assistant_db.read_markdown(project_source)
    return {
        "path": str(source.relative_to(root)),
        "metadata": metadata,
        "project": project,
        "body": body,
    }


def _inside(target: Path, parent: Path) -> bool:
    try:
        return target == parent or parent in target.parents
    except OSError:
        return False


def _allowed_asset_roots(root: Path, task_path: Path) -> list[Path]:
    allowed = [root.resolve()]
    metadata, _ = assistant_db.read_markdown(task_path)
    project_id = str(metadata.get("project") or task_path.parent.parent.name)
    project_source = root / "projects" / project_id / "project.md"
    if project_source.is_file():
        project, _ = assistant_db.read_markdown(project_source)
        for key in ("workspace_path", "project_path"):
            raw = project.get(key)
            if isinstance(raw, str) and raw:
                allowed.append(Path(raw).expanduser().resolve())
    for row in paths.read_workspace_registry().get("workspaces") or []:
        raw = row.get("path")
        if isinstance(raw, str) and raw:
            allowed.append(Path(raw).expanduser().resolve())
    return allowed


@router.get("/asset")
def get_asset(task: str, src: str, request: Request):
    root = _require_root(request)
    task_path = _safe_task_path(root, task)
    parsed = urlparse(src)
    if parsed.scheme or parsed.netloc:
        raise HTTPException(status_code=400, detail="remote assets are loaded directly")
    raw = Path(src).expanduser()
    target = raw.resolve() if raw.is_absolute() else (task_path.parent / raw).resolve()
    if not any(_inside(target, allowed) for allowed in _allowed_asset_roots(root, task_path)):
        raise HTTPException(status_code=403, detail="asset is outside Assistant/project roots")
    if not target.is_file():
        raise HTTPException(status_code=404, detail="asset not found")
    return FileResponse(target)
