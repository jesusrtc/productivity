from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from lab import paths

from core import fsguard


router = APIRouter()


class WorkspaceUseRequest(BaseModel):
    id: str | None = None
    path: str | None = None


def _workspace_id_for(root: Path, rows: list[dict]) -> str:
    resolved = root.expanduser().resolve()
    for row in rows:
        try:
            if Path(str(row["path"])).expanduser().resolve() == resolved:
                return str(row["id"])
        except (OSError, KeyError):
            continue
    return resolved.name


def _workspace_row(root: Path, rows: list[dict]) -> dict:
    resolved = root.expanduser().resolve()
    wid = _workspace_id_for(resolved, rows)
    for row in rows:
        try:
            if Path(str(row["path"])).expanduser().resolve() == resolved:
                return {
                    "id": str(row["id"]),
                    "name": str(row.get("name") or row["id"]),
                    "path": str(resolved),
                    "active": True,
                    "exists": resolved.is_dir(),
                }
        except (OSError, KeyError):
            continue
    return {
        "id": wid,
        "name": resolved.name,
        "path": str(resolved),
        "active": True,
        "exists": resolved.is_dir(),
    }


def _payload(request: Request) -> dict:
    cache = request.app.state.index_cache
    current_root = Path(cache.root).expanduser().resolve()
    data = paths.read_workspace_registry()
    rows = list(data.get("workspaces") or [])
    current = _workspace_row(current_root, rows)

    seen: set[str] = set()
    workspaces: list[dict] = []
    for row in rows:
        try:
            root = Path(str(row["path"])).expanduser().resolve()
        except OSError:
            root = Path(str(row["path"])).expanduser()
        key = str(root)
        seen.add(key)
        workspaces.append({
            "id": str(row["id"]),
            "name": str(row.get("name") or row["id"]),
            "path": key,
            "active": key == current["path"],
            "exists": root.is_dir(),
        })
    if current["path"] not in seen:
        workspaces.insert(0, current)
    return {
        "active": current["id"],
        "current": current,
        "workspaces": workspaces,
    }


def _resolve_requested_workspace(body: WorkspaceUseRequest) -> Path:
    if body.id:
        data = paths.read_workspace_registry()
        for row in data.get("workspaces") or []:
            if str(row.get("id")) == body.id:
                return Path(str(row["path"])).expanduser().resolve()
        raise HTTPException(status_code=404, detail=f"workspace {body.id!r} not found")
    if body.path:
        return Path(body.path).expanduser().resolve()
    raise HTTPException(status_code=400, detail="workspace id or path required")


def _validate_workspace(root: Path) -> None:
    if not root.is_dir():
        raise HTTPException(status_code=404, detail=f"workspace path not found: {root}")
    if not (root / "lab.toml").is_file() and not (root / "content").is_dir():
        raise HTTPException(status_code=400, detail=f"{root} is not a Lab workspace")


@router.get("/api/workspaces")
def list_workspaces(request: Request) -> dict:
    return _payload(request)


@router.post("/api/workspaces/use")
def use_workspace(body: WorkspaceUseRequest, request: Request) -> dict:
    root = _resolve_requested_workspace(body)
    _validate_workspace(root)
    paths.register_workspace(root, name=root.name, active=True)
    request.app.state.switch_workspace(root)
    return _payload(request)


def _scan_project_ids(root: Path) -> list[str]:
    """List project directory names under ``root/projects``.

    Runs entirely inside ``fsguard.guarded()`` -- including the ``is_dir()``
    check -- so a stalled/wedged volume can't hang on that first stat call
    either; only ``guarded()``'s timeout ever gets to observe it.
    """
    projects_dir = root / "projects"
    if not projects_dir.is_dir():
        return []
    return sorted(
        p.name for p in projects_dir.iterdir()
        if p.is_dir() and not p.name.startswith(".")
    )


@router.get("/api/workspaces/projects")
def list_workspace_projects(request: Request) -> dict:
    """All registered workspaces, each with its project ids.

    One dead/stalled volume must not blank the whole dashboard: a per-
    workspace scan that fails with fsguard's 503 is caught here and turned
    into ``unavailable: true`` (empty ``projects``) for that entry only,
    while every other workspace's listing still comes back normally.
    """
    payload = _payload(request)
    workspaces: list[dict] = []
    for row in payload["workspaces"]:
        entry = dict(row)
        root = Path(str(row["path"]))
        try:
            entry["projects"] = fsguard.guarded(root, _scan_project_ids, root)
            entry["unavailable"] = False
        except HTTPException as exc:
            if exc.status_code != 503:
                raise
            entry["projects"] = []
            entry["unavailable"] = True
            entry["detail"] = exc.detail
        workspaces.append(entry)
    return {"active": payload["active"], "workspaces": workspaces}
