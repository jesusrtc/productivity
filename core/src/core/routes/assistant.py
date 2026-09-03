"""API for the client-owned global Assistant task database."""
from __future__ import annotations

import os
import re
from pathlib import Path
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from lab import assistant as assistant_db
from lab import paths

from core import auth


router = APIRouter(prefix="/api/assistant")

_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^\s)]+)(?:\s+['\"][^)]*['\"])?\)")
_GENERATE_CONTENT_RE = re.compile(r"(?im)^#{1,3}\s+generate content\s*$")


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
        if not line or line.startswith("#") or line.startswith("```") or line.startswith("!["):
            continue
        line = line.removeprefix("- [ ] ").removeprefix("- [x] ").removeprefix("- ")
        parts.append(line)
        if len(" ".join(parts)) >= limit:
            break
    text = " ".join(parts)
    return text[:limit].rstrip() + ("…" if len(text) > limit else "")


def _first_image(body: str) -> dict[str, str] | None:
    match = _IMAGE_RE.search(body)
    if not match:
        return None
    return {"alt": match.group(1).strip(), "src": match.group(2).strip()}


def _task_sort_key(task: dict) -> tuple:
    status_order = {
        "in_progress": 0,
        "ready_to_review": 1,
        "ready": 2,
        "inbox": 3,
        "blocked": 4,
        "waiting": 5,
        "done": 6,
    }
    priority_order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    return (
        status_order.get(str(task.get("status")), 99),
        priority_order.get(str(task.get("priority")), 99),
        -float(task.get("mtime") or 0),
    )


class AssistantConfigBody(BaseModel):
    path: str
    create: bool = True


def _validate_config_root(raw: str) -> Path:
    if not raw.strip():
        raise HTTPException(status_code=400, detail="Assistant folder is required")
    source = Path(raw.strip()).expanduser()
    if not source.is_absolute():
        raise HTTPException(status_code=400, detail="Assistant folder must be an absolute path")
    try:
        target = source.resolve()
        framework = paths.find_framework_root().resolve()
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid Assistant folder: {exc}") from exc
    if target == framework or framework in target.parents or target in framework.parents:
        raise HTTPException(
            status_code=400,
            detail="Assistant data must live outside the Lab framework checkout",
        )
    return target


@router.put("/config")
def configure_assistant(body: AssistantConfigBody, request: Request) -> dict:
    """Select and initialize the one client-global Assistant folder."""
    auth.require_admin(request)
    target = _validate_config_root(body.path)
    if target.exists() and not target.is_dir():
        raise HTTPException(status_code=400, detail="Assistant path is not a folder")
    if not target.exists() and not body.create:
        raise HTTPException(status_code=404, detail="Assistant folder does not exist")
    try:
        assistant_db.initialize(target)
        paths.set_client_env_value(
            paths.find_framework_root(), "LAB_ASSISTANT_HOME", str(target),
        )
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"Could not configure Assistant: {exc}") from exc
    # Make the selection effective for this process as well as future starts.
    os.environ["LAB_ASSISTANT_HOME"] = str(target)
    return get_assistant(request)


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
            "meetings": [],
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
            "meetings": [],
            "statuses": list(assistant_db.STATUSES),
            "priorities": list(assistant_db.PRIORITIES),
        }

    projects = list(assistant_db.iter_projects(root))
    tasks = []
    for task in assistant_db.iter_tasks(root, projects):
        row = dict(task)
        body = str(row.pop("body", ""))
        for key in ("subtasks", "first_class_subtasks"):
            children = []
            for child in row.get(key) or []:
                item = dict(child)
                child_body = str(item.pop("body", ""))
                if item.get("document_backed"):
                    item["summary"] = _summary(child_body)
                    item["tldr"] = str(item.get("tldr") or item["summary"])
                    item["has_generated_content"] = bool(_GENERATE_CONTENT_RE.search(child_body))
                children.append(item)
            row[key] = children
        row["summary"] = _summary(body)
        row["tldr"] = str(row.get("tldr") or row["summary"])
        row["preview_image"] = _first_image(body)
        row["has_generated_content"] = bool(_GENERATE_CONTENT_RE.search(body))
        tasks.append(row)
    tasks.sort(key=_task_sort_key)
    meetings = []
    for meeting in assistant_db.iter_meetings(root, projects):
        row = dict(meeting)
        body = str(row.pop("body", ""))
        row["summary"] = _summary(body)
        meetings.append(row)
    meetings.sort(
        key=lambda row: (str(row.get("date") or ""), float(row.get("mtime") or 0)),
        reverse=True,
    )
    return {
        "configured": True,
        "exists": True,
        "initialized": (root / "AGENTS.md").is_file(),
        "root": str(root),
        "projects": projects,
        "tasks": tasks,
        "meetings": meetings,
        "statuses": list(assistant_db.STATUSES),
        "priorities": list(assistant_db.PRIORITIES),
    }


def _safe_markdown_path(root: Path, relative: str, collection: str | None = None) -> Path:
    rel = Path(relative)
    if rel.is_absolute() or ".." in rel.parts or rel.suffix.lower() != ".md":
        raise HTTPException(status_code=400, detail="invalid Assistant document path")
    if len(rel.parts) != 4 or rel.parts[0] != "projects":
        raise HTTPException(status_code=400, detail="invalid Assistant document path")
    if collection and rel.parts[-2] != collection:
        raise HTTPException(status_code=400, detail=f"invalid {collection} path")
    target = (root / rel).resolve()
    if root.resolve() not in target.parents:
        raise HTTPException(status_code=400, detail="document path escapes Assistant database")
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Assistant document not found")
    return target


def _safe_task_path(root: Path, relative: str) -> Path:
    return _safe_markdown_path(root, relative, "tasks")


def _safe_subtask_path(root: Path, relative: str) -> Path:
    return _safe_markdown_path(root, relative, "subtasks")


def _safe_meeting_path(root: Path, relative: str) -> Path:
    return _safe_markdown_path(root, relative, "meetings")


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
    subtasks = []
    parent_id = str(metadata.get("id") or source.stem)
    for child in assistant_db.iter_subtasks(root):
        if str(child.get("project")) != project_id or str(child.get("parent")) != parent_id:
            continue
        item = dict(child)
        child_body = str(item.pop("body", ""))
        item["summary"] = _summary(child_body)
        item["tldr"] = str(item.get("tldr") or item["summary"])
        item["has_generated_content"] = bool(_GENERATE_CONTENT_RE.search(child_body))
        subtasks.append(item)
    subtasks.sort(key=_task_sort_key)
    return {
        "path": str(source.relative_to(root)),
        "metadata": metadata,
        "project": project,
        "body": body,
        "tldr": str(metadata.get("tldr") or _summary(body)),
        "subtasks": subtasks,
    }


@router.get("/meeting")
def get_meeting(path: str, request: Request) -> dict:
    root = _require_root(request)
    source = _safe_meeting_path(root, path)
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
        "tldr": str(metadata.get("tldr") or _summary(body)),
    }


@router.get("/subtask")
def get_subtask(path: str, request: Request) -> dict:
    root = _require_root(request)
    source = _safe_subtask_path(root, path)
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
        "tldr": str(metadata.get("tldr") or _summary(body)),
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
    task_path = _safe_markdown_path(root, task)
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
