from __future__ import annotations

import json
import os
import hashlib
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from lab import paths
from lab import settings as lab_settings

from core import fsguard
from core import workspace_config
from core.diff_parser import get_registered_repos


router = APIRouter()


class WorkspaceUseRequest(BaseModel):
    id: str | None = None
    path: str | None = None


class WorkspaceAgentsPatch(BaseModel):
    supported: list[str]
    workspace: str | None = None


class WorkspaceAppearancePatch(BaseModel):
    name: str
    color: str


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
    # Advisory workspace.json status for the ACTIVE workspace only. Other
    # registered roots may live on unplugged volumes; reading a file there
    # would hang the whole dashboard, so they are not touched here.
    try:
        current["config"] = fsguard.guarded(
            current_root,
            workspace_config.summarize_workspace_config,
            current_root,
        )
    except HTTPException:
        pass
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


def _workspace_root(request: Request, workspace: str | None = None) -> Path:
    active_root = Path(request.app.state.index_cache.root).expanduser().resolve()
    if not workspace:
        return active_root
    for row in _payload(request)["workspaces"]:
        if row["id"] == workspace:
            root = Path(str(row["path"])).expanduser().resolve()
            _validate_workspace(root)
            return root
    raise HTTPException(status_code=404, detail=f"workspace {workspace!r} not found")


_WORKSPACE_COLORS = (
    "#58a6ff", "#a371f7", "#3fb950", "#d29922",
    "#f78166", "#db61a2", "#39c5cf", "#8b949e",
)


def _default_workspace_color(workspace_id: str) -> str:
    digest = hashlib.sha1(workspace_id.encode("utf-8")).digest()
    return _WORKSPACE_COLORS[int.from_bytes(digest, "big") % len(_WORKSPACE_COLORS)]


def _workspace_overview(root: Path, fallback_name: str, workspace_id: str) -> dict:
    projects = _scan_project_ids(root)
    loaded = workspace_config.load_workspace_config(root)
    doc = loaded.get("config") if isinstance(loaded.get("config"), dict) else {}
    display = doc.get("display") if isinstance(doc.get("display"), dict) else {}
    name = doc.get("name") if isinstance(doc.get("name"), str) and doc.get("name").strip() else fallback_name
    color = display.get("color") if isinstance(display.get("color"), str) else _default_workspace_color(workspace_id)

    project_rows: list[dict] = []
    for project in get_registered_repos(root):
        repos = [
            {"path": repo, "name": Path(repo).name, "branch": ""}
            for repo in (project.get("repos") or [])
        ]
        project_rows.append({
            **project,
            "repos": repos,
            "workspace": workspace_id,
            "workspace_name": name,
            "workspace_color": color,
            "workspace_path": str(root),
        })
    return {
        "projects": projects,
        "project_rows": project_rows,
        "name": name,
        "color": color,
        "config": {
            "present": loaded["present"],
            "valid": loaded["valid"],
            "errors": loaded["errors"],
            "warnings": loaded["warnings"],
        },
    }


@router.get("/api/workspaces")
def list_workspaces(request: Request) -> dict:
    return _payload(request)


@router.get("/api/workspace/config")
def get_workspace_config(request: Request, workspace: str | None = None) -> dict:
    """Full workspace.json load result (parsed document + validation) for the
    active workspace. The file is optional; ``present: false`` is a normal,
    valid answer."""
    root = _workspace_root(request, workspace)
    result = fsguard.guarded(root, workspace_config.load_workspace_config, root)
    return {"root": str(root), **result}


def _workspace_agent_policy(root: Path) -> dict:
    supported = workspace_config.supported_agents(root)
    default = lab_settings.resolve_agent(root)
    if default not in supported:
        default = supported[0]
    return {
        "root": str(root),
        "supported": supported,
        "default": default,
    }


@router.get("/api/workspace/agents")
def get_workspace_agents(request: Request, workspace: str | None = None) -> dict:
    """Return the effective agent choices for the active workspace."""
    root = _workspace_root(request, workspace)
    return fsguard.guarded(root, _workspace_agent_policy, root)


def _write_starter_workspace_config(root: Path) -> None:
    """Write a minimal valid workspace.json reflecting the workspace's
    current identity and agent settings. Atomic; never overwrites."""
    rows = list(paths.read_workspace_registry().get("workspaces") or [])
    row = _workspace_row(root, rows)
    settings = lab_settings.load(root)
    doc = {
        "version": 1,
        "id": row["id"],
        "name": row["name"],
        "agents": {
            "supported": list(lab_settings.VALID_AGENTS),
            "default": settings.get("defaultAgent") or lab_settings.DEFAULT_AGENT,
        },
    }
    path = root / "workspace.json"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _write_workspace_agents(root: Path, supported: list[str]) -> dict:
    if not (root / "workspace.json").exists():
        _write_starter_workspace_config(root)
    workspace_config.update_supported_agents(
        root,
        supported,
        lab_settings.resolve_agent(root),
    )
    return _workspace_agent_policy(root)


@router.post("/api/workspace/agents")
def update_workspace_agents(body: WorkspaceAgentsPatch, request: Request) -> dict:
    """Replace the active workspace's enabled-agent set.

    The rest of ``workspace.json`` is preserved. The last enabled agent cannot
    be removed because every terminal menu needs a valid fallback.
    """
    root = _workspace_root(request, body.workspace)
    try:
        return fsguard.guarded(
            root,
            _write_workspace_agents,
            root,
            body.supported,
        )
    except workspace_config.WorkspaceConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/workspace/config/init")
def init_workspace_config(request: Request, workspace: str | None = None) -> dict:
    """Create a starter workspace.json at the active workspace root.

    Bootstrap only: 409 when the file already exists — edits and the real
    configuration work belong to the user's agent (the Workspace tab's
    setup prompt explains the structure to it)."""
    root = _workspace_root(request, workspace)
    if (root / "workspace.json").exists():
        raise HTTPException(status_code=409, detail="workspace.json already exists")
    fsguard.guarded(root, _write_starter_workspace_config, root)
    result = fsguard.guarded(root, workspace_config.load_workspace_config, root)
    return {"root": str(root), **result}


@router.patch("/api/workspaces/{workspace_id}/appearance")
def update_workspace_appearance(
    workspace_id: str, body: WorkspaceAppearancePatch, request: Request,
) -> dict:
    root = _workspace_root(request, workspace_id)
    try:
        result = fsguard.guarded(
            root, workspace_config.update_appearance, root, body.name, body.color,
        )
    except workspace_config.WorkspaceConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    doc = result.get("config") or {}
    display = doc.get("display") if isinstance(doc.get("display"), dict) else {}
    return {
        "id": workspace_id,
        "name": doc.get("name") or workspace_id,
        "color": display.get("color") or _default_workspace_color(workspace_id),
        "path": str(root),
    }


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
            overview = fsguard.guarded(
                root, _workspace_overview, root, entry["name"], entry["id"],
            )
            entry.update(overview)
            entry["unavailable"] = False
        except HTTPException as exc:
            if exc.status_code != 503:
                raise
            entry["projects"] = []
            entry["project_rows"] = []
            entry["color"] = _default_workspace_color(entry["id"])
            entry["unavailable"] = True
            entry["detail"] = exc.detail
        workspaces.append(entry)
    return {"active": payload["active"], "workspaces": workspaces}
