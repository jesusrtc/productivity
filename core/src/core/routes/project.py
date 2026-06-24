from __future__ import annotations

import re
from datetime import date, datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from lab import paths, storage
from lab.model import ModelError, Project, validate_id


router = APIRouter()


_DURATION_RE = re.compile(r"^\s*(\d+)\s*([mhdw])\s*$", re.IGNORECASE)


def _now_local() -> datetime:
    return datetime.now(tz=timezone.utc).astimezone()


def _duration_to_iso(spec: str, now: datetime) -> str:
    m = _DURATION_RE.match(spec)
    if not m:
        raise HTTPException(
            status_code=400,
            detail=f"duration {spec!r}: expected N followed by m/h/d/w",
        )
    qty = int(m.group(1))
    unit = m.group(2).lower()
    from datetime import timedelta
    seconds = {"m": 60, "h": 3600, "d": 86400, "w": 604800}[unit] * qty
    return (now + timedelta(seconds=seconds)).isoformat(timespec="seconds")


def _normalize_until(spec: str) -> str:
    spec = spec.strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}$", spec):
        d = date.fromisoformat(spec)
        local_tz = _now_local().tzinfo
        dt = datetime(d.year, d.month, d.day, 23, 59, 0, tzinfo=local_tz)
        return dt.isoformat(timespec="seconds")
    try:
        dt = datetime.fromisoformat(spec.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"invalid until: {spec!r}") from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_now_local().tzinfo)
    return dt.isoformat(timespec="seconds")


def _validate_project_id(project_id: str) -> None:
    try:
        validate_id(project_id)
    except ModelError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _root_for_project(root: Path, project_id: str) -> Path:
    if project_id == paths.SELF_PROJECT_ID:
        return paths.find_framework_root()
    return root


@router.get("/api/projects")
def list_projects(request: Request, status: str | None = None,
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
def get_project(project_id: str, request: Request) -> dict:
    _validate_project_id(project_id)
    root: Path = request.app.state.index_cache.root
    root = _root_for_project(root, project_id)
    if paths.is_pseudo_project(project_id):
        paths.ensure_self_files(root)
    pjson = paths.project_file(root, project_id)
    if not pjson.is_file():
        raise HTTPException(status_code=404, detail=f"project {project_id!r} not found")
    return storage.read_json(pjson)


@router.get("/api/projects/{project_id}/tasks")
def get_project_tasks(project_id: str, request: Request) -> dict:
    _validate_project_id(project_id)
    root: Path = request.app.state.index_cache.root
    root = _root_for_project(root, project_id)
    if paths.is_pseudo_project(project_id):
        paths.ensure_self_files(root)
    tjson = paths.tasks_file(root, project_id)
    if not tjson.is_file():
        raise HTTPException(status_code=404, detail=f"project {project_id!r} not found")
    return storage.read_json(tjson)


@router.get("/api/projects/{project_id}/docs")
def list_project_docs(project_id: str, request: Request) -> list[dict]:
    _validate_project_id(project_id)
    root: Path = request.app.state.index_cache.root
    root = _root_for_project(root, project_id)
    pdir = paths.project_dir(root, project_id)
    if not pdir.is_dir():
        raise HTTPException(status_code=404, detail=f"project {project_id!r} not found")

    out: list[dict] = []
    for sub in ("docs", "notes", "assets", "notebooks"):
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


class HoldBody(BaseModel):
    until: str | None = None         # ISO date or datetime
    duration: str | None = None      # e.g. "2h", "3d" (mutually exclusive with until)
    reason: str | None = None
    url: str | None = None


@router.post("/api/projects/{project_id}/hold")
def set_project_hold(project_id: str, body: HoldBody, request: Request) -> dict:
    """Set (or replace) a soft-snooze hold on a project.

    The project stays visible everywhere; the UI uses ``hold.until`` to
    sort held projects out of the active set until the timestamp passes,
    at which point they resurface in the "Ready for review" strip.
    """
    _validate_project_id(project_id)
    if bool(body.until) == bool(body.duration):
        raise HTTPException(
            status_code=400,
            detail="exactly one of `until` or `duration` is required",
        )
    root: Path = request.app.state.index_cache.root
    root = _root_for_project(root, project_id)
    pjson = paths.project_file(root, project_id)
    if not pjson.is_file():
        raise HTTPException(status_code=404, detail=f"project {project_id!r} not found")
    data = storage.read_json(pjson)

    now = _now_local()
    until_iso = _duration_to_iso(body.duration, now) if body.duration else _normalize_until(body.until)

    hold_doc: dict = {"until": until_iso, "set_at": now.isoformat(timespec="seconds")}
    if body.reason:
        hold_doc["reason"] = body.reason.strip()
    if body.url:
        hold_doc["url"] = body.url.strip()
    data["hold"] = hold_doc
    data["updated"] = date.today().isoformat()

    try:
        Project.from_dict(data)
    except ModelError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    storage.write_json(pjson, data)
    return {"ok": True, "hold": hold_doc}


@router.delete("/api/projects/{project_id}/hold")
def clear_project_hold(project_id: str, request: Request) -> dict:
    """Remove the project's hold (no-op if nothing is set)."""
    _validate_project_id(project_id)
    root: Path = request.app.state.index_cache.root
    root = _root_for_project(root, project_id)
    pjson = paths.project_file(root, project_id)
    if not pjson.is_file():
        raise HTTPException(status_code=404, detail=f"project {project_id!r} not found")
    data = storage.read_json(pjson)
    if data.get("hold"):
        data["hold"] = None
        data["updated"] = date.today().isoformat()
        storage.write_json(pjson, data)
    return {"ok": True}


class AgentBody(BaseModel):
    agent: str | None = None   # None / "" → clear the override (inherit global)
    model: str | None = None


@router.post("/api/projects/{project_id}/agent")
def set_project_agent(project_id: str, body: AgentBody, request: Request) -> dict:
    """Set or clear a project's agent/model override.

    Empty/None values clear the override so the project inherits the global
    default from ``.agents/config.json``. Agent is validated against
    ``VALID_AGENTS`` via the Project model.
    """
    _validate_project_id(project_id)
    root: Path = request.app.state.index_cache.root
    root = _root_for_project(root, project_id)
    pjson = paths.project_file(root, project_id)
    if not pjson.is_file():
        raise HTTPException(status_code=404, detail=f"project {project_id!r} not found")
    data = storage.read_json(pjson)
    data["agent"] = body.agent or None
    data["model"] = body.model or None
    data["updated"] = date.today().isoformat()
    try:
        Project.from_dict(data)
    except ModelError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    storage.write_json(pjson, data)
    return {"ok": True, "agent": data["agent"], "model": data["model"]}


@router.get("/api/projects/{project_id}/file")
def get_project_file(project_id: str, path: str, request: Request):
    _validate_project_id(project_id)
    if path.startswith("/") or ".." in Path(path).parts:
        raise HTTPException(status_code=400, detail="invalid path")
    root: Path = request.app.state.index_cache.root
    root = _root_for_project(root, project_id)
    pdir = paths.project_dir(root, project_id)
    target = (pdir / path).resolve()
    if pdir.resolve() not in target.parents and target != pdir.resolve():
        raise HTTPException(status_code=400, detail="path escapes project")
    if not target.is_file():
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(target)
