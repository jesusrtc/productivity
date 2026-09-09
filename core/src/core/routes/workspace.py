from __future__ import annotations

import re
from datetime import date, datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from lab import paths, storage
from lab.model import ModelError, Workspace, validate_id

from core import auth, fsguard, vault_config


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


def _validate_workspace_id(workspace_id: str) -> None:
    try:
        validate_id(workspace_id)
    except ModelError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _root_for_workspace(root: Path, workspace_id: str) -> Path:
    if workspace_id == paths.SELF_WORKSPACE_ID:
        return paths.find_framework_root()
    return root


@router.get("/api/workspaces")
def list_workspaces(request: Request, status: str | None = None,
                  tag: str | None = None, label: str | None = None) -> list[dict]:
    idx = auth.request_index(request)
    rows = idx["workspaces"]
    if status:
        rows = [r for r in rows if r.get("status") == status]
    if tag:
        rows = [r for r in rows if tag in (r.get("tags") or [])]
    if label:
        rows = [r for r in rows if label in (r.get("labels") or [])]
    return rows


@router.get("/api/workspaces/{workspace_id}")
def get_workspace(workspace_id: str, request: Request) -> dict:
    _validate_workspace_id(workspace_id)
    root = auth.request_root(request)
    root = _root_for_workspace(root, workspace_id)
    if paths.is_pseudo_workspace(workspace_id):
        paths.ensure_self_files(root)
    pjson = paths.workspace_file(root, workspace_id)
    if not pjson.is_file():
        raise HTTPException(status_code=404, detail=f"workspace {workspace_id!r} not found")
    return storage.read_json(pjson)


@router.get("/api/workspaces/{workspace_id}/tasks")
def get_workspace_tasks(workspace_id: str, request: Request) -> dict:
    _validate_workspace_id(workspace_id)
    root = auth.request_root(request)
    root = _root_for_workspace(root, workspace_id)
    if paths.is_pseudo_workspace(workspace_id):
        paths.ensure_self_files(root)
    tjson = paths.tasks_file(root, workspace_id)
    if not tjson.is_file():
        raise HTTPException(status_code=404, detail=f"workspace {workspace_id!r} not found")
    return storage.read_json(tjson)


@router.get("/api/workspaces/{workspace_id}/docs")
def list_workspace_docs(workspace_id: str, request: Request) -> list[dict]:
    _validate_workspace_id(workspace_id)
    root = auth.request_root(request)
    root = _root_for_workspace(root, workspace_id)
    pdir = paths.workspace_dir(root, workspace_id)
    if not pdir.is_dir():
        raise HTTPException(status_code=404, detail=f"workspace {workspace_id!r} not found")

    def _scan_docs() -> list[dict]:
        found: list[dict] = []
        for sub in ("docs", "notes", "assets", "notebooks"):
            sub_dir = pdir / sub
            if not sub_dir.is_dir():
                continue
            for f in sorted(sub_dir.rglob("*")):
                if f.is_file():
                    found.append({
                        "path": str(f.relative_to(pdir)),
                        "size": f.stat().st_size,
                    })
        return found

    return fsguard.guarded(root, _scan_docs)


class HoldBody(BaseModel):
    until: str | None = None         # ISO date or datetime
    duration: str | None = None      # e.g. "2h", "3d" (mutually exclusive with until)
    reason: str | None = None
    url: str | None = None


@router.post("/api/workspaces/{workspace_id}/hold")
def set_workspace_hold(workspace_id: str, body: HoldBody, request: Request) -> dict:
    """Set (or replace) a soft-snooze hold on a workspace.

    The workspace stays visible everywhere; the UI uses ``hold.until`` to
    sort held workspaces out of the active set until the timestamp passes,
    at which point they resurface in the "Ready for review" strip.
    """
    _validate_workspace_id(workspace_id)
    if bool(body.until) == bool(body.duration):
        raise HTTPException(
            status_code=400,
            detail="exactly one of `until` or `duration` is required",
        )
    root = auth.request_root(request)
    root = _root_for_workspace(root, workspace_id)
    pjson = paths.workspace_file(root, workspace_id)
    if not pjson.is_file():
        raise HTTPException(status_code=404, detail=f"workspace {workspace_id!r} not found")
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
        Workspace.from_dict(data)
    except ModelError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    storage.write_json(pjson, data)
    return {"ok": True, "hold": hold_doc}


@router.delete("/api/workspaces/{workspace_id}/hold")
def clear_workspace_hold(workspace_id: str, request: Request) -> dict:
    """Remove the workspace's hold (no-op if nothing is set)."""
    _validate_workspace_id(workspace_id)
    root = auth.request_root(request)
    root = _root_for_workspace(root, workspace_id)
    pjson = paths.workspace_file(root, workspace_id)
    if not pjson.is_file():
        raise HTTPException(status_code=404, detail=f"workspace {workspace_id!r} not found")
    data = storage.read_json(pjson)
    if data.get("hold"):
        data["hold"] = None
        data["updated"] = date.today().isoformat()
        storage.write_json(pjson, data)
    return {"ok": True}


class AgentBody(BaseModel):
    agent: str | None = None   # None / "" → clear the override (inherit global)
    model: str | None = None


@router.post("/api/workspaces/{workspace_id}/agent")
def set_workspace_agent(workspace_id: str, body: AgentBody, request: Request) -> dict:
    """Set or clear a workspace's agent/model override.

    Empty/None values clear the override so the workspace inherits the global
    default from ``.agents/config.json``. Agent is validated against
    ``VALID_AGENTS`` via the Workspace model.
    """
    _validate_workspace_id(workspace_id)
    root = auth.request_root(request)
    root = _root_for_workspace(root, workspace_id)
    if body.agent and body.agent not in vault_config.supported_agents(root):
        raise HTTPException(
            status_code=400,
            detail=f"agent {body.agent!r} is not enabled for this vault",
        )
    pjson = paths.workspace_file(root, workspace_id)
    if not pjson.is_file():
        raise HTTPException(status_code=404, detail=f"workspace {workspace_id!r} not found")
    data = storage.read_json(pjson)
    data["agent"] = body.agent or None
    data["model"] = body.model or None
    data["updated"] = date.today().isoformat()
    try:
        Workspace.from_dict(data)
    except ModelError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    storage.write_json(pjson, data)
    return {"ok": True, "agent": data["agent"], "model": data["model"]}


@router.get("/api/workspaces/{workspace_id}/file")
def get_workspace_file(workspace_id: str, path: str, request: Request):
    _validate_workspace_id(workspace_id)
    if path.startswith("/") or ".." in Path(path).parts:
        raise HTTPException(status_code=400, detail="invalid path")
    root = auth.request_root(request)
    root = _root_for_workspace(root, workspace_id)
    pdir = paths.workspace_dir(root, workspace_id)
    target = (pdir / path).resolve()
    if pdir.resolve() not in target.parents and target != pdir.resolve():
        raise HTTPException(status_code=400, detail="path escapes workspace")
    if not target.is_file():
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(target)
