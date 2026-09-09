from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from lab import paths, storage
from lab.model import ModelError, validate_id

from core import auth


router = APIRouter()


def _run_lab(args: list[str], *, root: Path) -> None:
    """Invoke the lab CLI against ``root``. Raise HTTPException on non-zero.

    Uses ``sys.executable -m lab`` so the backend always runs the lab module
    from its own venv (which installs ``lab`` as a dependency), immune to
    PATH ordering issues (e.g. a stale ``lab`` shim earlier on PATH).
    """
    # LAB_VAULT has precedence over LAB_ROOT in the CLI. Set both so a
    # server launched with LAB_VAULT can still target another registered
    # vault for a single request without mutating global state.
    env = {**os.environ, "LAB_ROOT": str(root), "LAB_VAULT": str(root)}
    proc = subprocess.run(
        [sys.executable, "-m", "lab", *args],
        env=env,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        msg = (proc.stderr or proc.stdout).strip().removeprefix("Error: ")
        raise HTTPException(status_code=400, detail=msg or "lab command failed")


def _read_workspace(root: Path, workspace_id: str) -> dict:
    pjson = paths.workspace_file(root, workspace_id)
    return storage.read_json(pjson)


def _find_task(root: Path, workspace_id: str, task_id: int) -> dict:
    tjson = paths.tasks_file(root, workspace_id)
    doc = storage.read_json(tjson)
    for t in doc.get("tasks", []):
        if t["id"] == task_id:
            return t
    raise HTTPException(status_code=404, detail=f"task #{task_id} not found")


def _validate_pid(pid: str) -> None:
    try:
        validate_id(pid)
    except ModelError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _root_for_workspace(root: Path, workspace_id: str) -> Path:
    if workspace_id == paths.SELF_WORKSPACE_ID:
        return paths.find_framework_root()
    return root


def _root_for_vault(request: Request, vault: str | None) -> Path:
    """Resolve a registered vault without changing the active vault."""
    active_root = auth.request_root(request)
    if not vault:
        return active_root
    rows = paths.read_vault_registry().get("vaults") or []
    # The catalog includes the active root even before it has been registered,
    # using its directory name as the vault id. Accept that exact identity.
    active_id = active_root.name
    for row in rows:
        try:
            if Path(str(row["path"])).expanduser().resolve() == active_root:
                active_id = str(row["id"])
                break
        except (KeyError, OSError):
            continue
    if vault == active_id:
        return active_root
    for row in rows:
        if str(row.get("id")) != vault:
            continue
        root = Path(str(row["path"])).expanduser().resolve()
        if not root.is_dir():
            raise HTTPException(status_code=404, detail=f"vault path not found: {root}")
        if not (root / "lab.toml").is_file() and not (root / "content").is_dir():
            raise HTTPException(status_code=400, detail=f"{root} is not a Lab vault")
        return root
    raise HTTPException(status_code=404, detail=f"vault {vault!r} not found")


class NewWorkspace(BaseModel):
    id: str
    vault: str | None = None
    description: str = ""
    priority: str | None = None
    due: str | None = None
    tags: list[str] = Field(default_factory=list)
    labels: list[str] = Field(default_factory=list)


class WorkspaceField(BaseModel):
    field: str
    # None / empty → clear the field (supported for nullable fields only).
    value: str | None = None


class TabState(BaseModel):
    open: bool


# Whitelist of fields settable via the dashboard / attributes bar. Keep this
# in sync with lab's `workspace set` validator. `tags`/`labels` accept
# comma-separated strings on the wire, matching the CLI.
_WORKSPACE_SETTABLE_FIELDS = {
    "priority", "due", "loe", "description",
    "name", "status", "tags", "labels",
}


@router.post("/api/workspaces/{workspace_id}/field")
def update_workspace_field(workspace_id: str, body: WorkspaceField,
                         request: Request, vault: str | None = None) -> dict:
    """Partial update of a single workspace.json field.

    Wraps ``lab workspace set <id> <field> <value>`` so the same validation
    path governs API and CLI writes. Passing ``value=null`` (or ``""``)
    clears the field for nullable fields (priority/due/loe/description).
    """
    root = _root_for_vault(request, vault)
    _validate_pid(workspace_id)
    root = _root_for_workspace(root, workspace_id)
    if body.field not in _WORKSPACE_SETTABLE_FIELDS:
        raise HTTPException(
            status_code=400,
            detail=f"field {body.field!r} not settable via API (allowed: {sorted(_WORKSPACE_SETTABLE_FIELDS)})",
        )
    # `lab workspace set` expects a string value. Represent "clear" as the
    # empty string, which the CLI maps to None for nullable fields.
    value = "" if body.value is None else body.value
    _run_lab(["workspace", "set", workspace_id, body.field, value], root=root)
    return _read_workspace(root, workspace_id)


@router.post("/api/workspaces/{workspace_id}/tab")
def set_workspace_tab(workspace_id: str, body: TabState,
                    request: Request) -> dict:
    """Set the dashboard tab-open flag for a workspace.

    Persisted in ``workspace.json`` as ``tab_open`` so the topbar tab strip
    survives page reloads independently of whether the workspace has a live
    tmux session. Pure UI state — written directly via storage rather than
    through ``lab workspace set`` (which is the canonical-fields path).
    """
    root = auth.request_root(request)
    _validate_pid(workspace_id)
    root = _root_for_workspace(root, workspace_id)
    pjson = paths.workspace_file(root, workspace_id)
    if not pjson.is_file():
        raise HTTPException(status_code=404, detail=f"workspace {workspace_id!r} not found")
    data = storage.read_json(pjson)
    data["tab_open"] = bool(body.open)
    storage.write_json(pjson, data)
    return data


@router.post("/api/workspaces")
def create_workspace(body: NewWorkspace, request: Request) -> dict:
    root = _root_for_vault(request, body.vault)
    _validate_pid(body.id)
    args = ["workspace", "new", body.id]
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
    return _read_workspace(root, body.id)


class NewTask(BaseModel):
    workspace_id: str
    title: str
    priority: str
    loe: float | None = None
    due: str | None = None
    tags: list[str] = Field(default_factory=list)
    labels: list[str] = Field(default_factory=list)
    create_notes_file: bool = False


@router.post("/api/tasks")
def create_task(body: NewTask, request: Request) -> dict:
    root = auth.request_root(request)
    _validate_pid(body.workspace_id)
    root = _root_for_workspace(root, body.workspace_id)
    args = ["task", "new", body.title, "--workspace", body.workspace_id, "--priority", body.priority]
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

    tjson = paths.tasks_file(root, body.workspace_id)
    doc = storage.read_json(tjson)
    return doc["tasks"][-1]


class StatusChange(BaseModel):
    status: str
    reason: str | None = None


@router.post("/api/tasks/{workspace_id}/{task_id}/status")
def set_task_status(workspace_id: str, task_id: int, body: StatusChange,
                    request: Request) -> dict:
    root = auth.request_root(request)
    _validate_pid(workspace_id)
    root = _root_for_workspace(root, workspace_id)
    if body.status == "done":
        args = ["task", "done", str(task_id), "--workspace", workspace_id]
    elif body.status == "reopened":
        args = ["task", "reopen", str(task_id), "--workspace", workspace_id]
    elif body.status == "blocked":
        if not body.reason:
            raise HTTPException(status_code=400, detail="reason required when status=blocked")
        args = ["task", "block", str(task_id), body.reason, "--workspace", workspace_id]
    elif body.status == "in_progress":
        args = ["task", "unblock", str(task_id), "--workspace", workspace_id]
    else:
        raise HTTPException(status_code=400, detail=f"unsupported status transition: {body.status}")
    _run_lab(args, root=root)
    return _find_task(root, workspace_id, task_id)


class FieldUpdate(BaseModel):
    field: str
    value: str


@router.post("/api/tasks/{workspace_id}/{task_id}/update")
def update_task_field(workspace_id: str, task_id: int, body: FieldUpdate,
                      request: Request) -> dict:
    root = auth.request_root(request)
    _validate_pid(workspace_id)
    root = _root_for_workspace(root, workspace_id)
    args = ["task", "set", str(task_id), body.field, body.value, "--workspace", workspace_id]
    _run_lab(args, root=root)
    return _find_task(root, workspace_id, task_id)


class NewPR(BaseModel):
    url: str
    mp: str = ""
    title: str = ""
    status: str = "open"


@router.post("/api/workspaces/{workspace_id}/prs")
def add_pr(workspace_id: str, body: NewPR, request: Request) -> dict:
    root = auth.request_root(request)
    _validate_pid(workspace_id)
    root = _root_for_workspace(root, workspace_id)
    args = [
        "pr", "add", body.url, "--workspace", workspace_id,
        "--mp", body.mp, "--title", body.title, "--status", body.status,
    ]
    _run_lab(args, root=root)
    return _read_workspace(root, workspace_id)


@router.delete("/api/workspaces/{workspace_id}/prs/{idx}")
def rm_pr(workspace_id: str, idx: int, request: Request) -> dict:
    root = auth.request_root(request)
    _validate_pid(workspace_id)
    root = _root_for_workspace(root, workspace_id)
    _run_lab(["pr", "rm", str(idx), "--workspace", workspace_id], root=root)
    return _read_workspace(root, workspace_id)


class NewArtifact(BaseModel):
    url: str
    type: str = "url"
    title: str = ""
    description: str = ""


@router.post("/api/workspaces/{workspace_id}/artifacts")
def add_artifact(workspace_id: str, body: NewArtifact, request: Request) -> dict:
    root = auth.request_root(request)
    _validate_pid(workspace_id)
    root = _root_for_workspace(root, workspace_id)
    args = [
        "artifact", "add", body.url, "--workspace", workspace_id,
        "--type", body.type, "--title", body.title, "--desc", body.description,
    ]
    _run_lab(args, root=root)
    return _read_workspace(root, workspace_id)


@router.delete("/api/workspaces/{workspace_id}/artifacts/{idx}")
def rm_artifact(workspace_id: str, idx: int, request: Request) -> dict:
    root = auth.request_root(request)
    _validate_pid(workspace_id)
    root = _root_for_workspace(root, workspace_id)
    _run_lab(["artifact", "rm", str(idx), "--workspace", workspace_id], root=root)
    return _read_workspace(root, workspace_id)
