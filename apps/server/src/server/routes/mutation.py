from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from lab import paths, storage
from lab.model import ModelError, validate_id


router = APIRouter()


def _run_lab(args: list[str], *, root: Path) -> None:
    """Invoke the lab CLI with LAB_ROOT set. Raise HTTPException on non-zero.

    Uses ``sys.executable -m lab`` so the backend always runs the lab module
    from its own venv (which installs ``lab`` as a dependency), immune to
    PATH ordering issues (e.g. a stale ``lab`` shim earlier on PATH).
    """
    env = {**os.environ, "LAB_ROOT": str(root)}
    proc = subprocess.run(
        [sys.executable, "-m", "lab", *args],
        env=env,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        msg = (proc.stderr or proc.stdout).strip().removeprefix("Error: ")
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


def _validate_pid(pid: str) -> None:
    try:
        validate_id(pid)
    except ModelError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class NewProject(BaseModel):
    id: str
    description: str = ""
    priority: str | None = None
    due: str | None = None
    tags: list[str] = Field(default_factory=list)
    labels: list[str] = Field(default_factory=list)


class ProjectField(BaseModel):
    field: str
    # None / empty → clear the field (supported for nullable fields only).
    value: str | None = None


class TabState(BaseModel):
    open: bool


# Whitelist of fields settable via the dashboard / attributes bar. Keep this
# in sync with lab's `project set` validator. `tags`/`labels` accept
# comma-separated strings on the wire, matching the CLI.
_PROJECT_SETTABLE_FIELDS = {
    "priority", "due", "loe", "description",
    "name", "status", "tags", "labels",
}


@router.post("/api/projects/{project_id}/field")
async def update_project_field(project_id: str, body: ProjectField,
                               request: Request) -> dict:
    """Partial update of a single project.json field.

    Wraps ``lab project set <id> <field> <value>`` so the same validation
    path governs API and CLI writes. Passing ``value=null`` (or ``""``)
    clears the field for nullable fields (priority/due/loe/description).
    """
    root: Path = request.app.state.index_cache.root
    _validate_pid(project_id)
    if body.field not in _PROJECT_SETTABLE_FIELDS:
        raise HTTPException(
            status_code=400,
            detail=f"field {body.field!r} not settable via API (allowed: {sorted(_PROJECT_SETTABLE_FIELDS)})",
        )
    # `lab project set` expects a string value. Represent "clear" as the
    # empty string, which the CLI maps to None for nullable fields.
    value = "" if body.value is None else body.value
    _run_lab(["project", "set", project_id, body.field, value], root=root)
    return _read_project(root, project_id)


@router.post("/api/projects/{project_id}/tab")
async def set_project_tab(project_id: str, body: TabState,
                          request: Request) -> dict:
    """Set the dashboard tab-open flag for a project.

    Persisted in ``project.json`` as ``tab_open`` so the topbar tab strip
    survives page reloads independently of whether the project has a live
    tmux session. Pure UI state — written directly via storage rather than
    through ``lab project set`` (which is the canonical-fields path).
    """
    root: Path = request.app.state.index_cache.root
    _validate_pid(project_id)
    pjson = paths.project_file(root, project_id)
    if not pjson.is_file():
        raise HTTPException(status_code=404, detail=f"project {project_id!r} not found")
    data = storage.read_json(pjson)
    data["tab_open"] = bool(body.open)
    storage.write_json(pjson, data)
    return data


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

    tjson = paths.tasks_file(root, body.project_id)
    doc = storage.read_json(tjson)
    return doc["tasks"][-1]


class StatusChange(BaseModel):
    status: str
    reason: str | None = None


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


class NewPR(BaseModel):
    url: str
    mp: str = ""
    title: str = ""
    status: str = "open"


@router.post("/api/projects/{project_id}/prs")
async def add_pr(project_id: str, body: NewPR, request: Request) -> dict:
    root: Path = request.app.state.index_cache.root
    _validate_pid(project_id)
    args = [
        "pr", "add", body.url, "--project", project_id,
        "--mp", body.mp, "--title", body.title, "--status", body.status,
    ]
    _run_lab(args, root=root)
    return _read_project(root, project_id)


@router.delete("/api/projects/{project_id}/prs/{idx}")
async def rm_pr(project_id: str, idx: int, request: Request) -> dict:
    root: Path = request.app.state.index_cache.root
    _validate_pid(project_id)
    _run_lab(["pr", "rm", str(idx), "--project", project_id], root=root)
    return _read_project(root, project_id)


class NewArtifact(BaseModel):
    url: str
    type: str = "url"
    title: str = ""
    description: str = ""


@router.post("/api/projects/{project_id}/artifacts")
async def add_artifact(project_id: str, body: NewArtifact, request: Request) -> dict:
    root: Path = request.app.state.index_cache.root
    _validate_pid(project_id)
    args = [
        "artifact", "add", body.url, "--project", project_id,
        "--type", body.type, "--title", body.title, "--desc", body.description,
    ]
    _run_lab(args, root=root)
    return _read_project(root, project_id)


@router.delete("/api/projects/{project_id}/artifacts/{idx}")
async def rm_artifact(project_id: str, idx: int, request: Request) -> dict:
    root: Path = request.app.state.index_cache.root
    _validate_pid(project_id)
    _run_lab(["artifact", "rm", str(idx), "--project", project_id], root=root)
    return _read_project(root, project_id)
