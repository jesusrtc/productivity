"""API for the client-owned global Assistant task database."""
from __future__ import annotations

from lab import naming, assistant_meetings as meeting_db, assistant_records as records, assistant_documents as documents
from core.routes import assistant_v2

import os
import re
from threading import Lock
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
    if records.manifest(root).get('state') == 'migrating':
        raise HTTPException(status_code=503, detail='Assistant migration in progress')
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
            "workspaces": [],
            "tasks": [],
            "meetings": [],
            "statuses": ["not_started","in_progress","done","cancelled"] if documents.enabled(root) else list(assistant_db.STATUSES),
            "priorities": list(assistant_db.PRIORITIES),
        }
    if not root.is_dir():
        return {
            "configured": True,
            "exists": False,
            "root": str(root),
            "workspaces": [],
            "tasks": [],
            "meetings": [],
            "statuses": ["not_started","in_progress","done","cancelled"] if documents.enabled(root) else list(assistant_db.STATUSES),
            "priorities": list(assistant_db.PRIORITIES),
        }

    if records.manifest(root).get('state') == 'migrating':
        raise HTTPException(status_code=503, detail='Assistant migration in progress')
    workspaces = list(assistant_db.iter_workspaces(root))
    tasks = []
    for task in assistant_db.iter_tasks(root, workspaces):
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
    meetings = meeting_db.list_rows(root, workspaces)
    series_rows = []
    for series in meeting_db.iter_series(root, workspaces):
        history = [row for row in meetings if row.get("series") == series["id"] and (records.enabled(root) or row["workspace"] == series["workspace"])]
        latest = None
        for row in history:
            try:
                latest = meeting_db.validate_date(row.get("date"))
                break
            except ValueError:
                continue
        series_rows.append({**{k: v for k, v in series.items() if k != "body"},
                            "latest_date": latest, "meeting_count": len(history)})
    return {
        "configured": True,
        "exists": True,
        "initialized": (root / "AGENTS.md").is_file(),
        "root": str(root),
        "workspaces": workspaces,
        "tasks": tasks,
        "meetings": meetings,
        "meeting_series": series_rows,
        "schema": 2 if records.enabled(root) else 1,
        "projects": list(records.records(root, "projects")) if records.enabled(root) else [],
        "notes": [{**row,"search_text":" ".join(str(child.get(field) or "") for child in [row,*records.descendants(list(records.records(root)),row)] for field in ("title","tldr","owner"))} for row in records.records(root, "notes") if not row.get("embedded") and row.get("note_type") in {"plain","thread","subtab"}] if records.enabled(root) else [],
        "statuses": ["not_started","in_progress","done","cancelled"] if documents.enabled(root) else list(assistant_db.STATUSES),
        "priorities": list(assistant_db.PRIORITIES),
    }


def _safe_markdown_path(root: Path, relative: str, collection: str | None = None) -> Path:
    if records.enabled(root):
        try:
            return records.resolve(root, relative, collection)[0]
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    rel = Path(relative)
    if rel.is_absolute() or ".." in rel.parts or rel.suffix.lower() != ".md":
        raise HTTPException(status_code=400, detail="invalid Assistant document path")
    if len(rel.parts) != 4 or rel.parts[0] != naming.workspaces_dir(root).name:
        raise HTTPException(status_code=400, detail="invalid Assistant document path")
    if collection and rel.parts[-2] != collection:
        raise HTTPException(status_code=400, detail=f"invalid {collection} path")
    if rel.parts[-2] in {"meetings", "meeting-series"}:
        try:
            meeting_db.safe_path(root, root / rel)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
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
    if records.enabled(root):
        return assistant_v2.detail(root, path, 'tasks')
    source = _safe_task_path(root, path)
    metadata, body = assistant_db.read_markdown(source)
    workspace_id = str(metadata.get("workspace") or source.parent.parent.name)
    workspace_source = naming.workspace_document_file(naming.workspaces_dir(root) / workspace_id)
    workspace: dict = {}
    if workspace_source.is_file():
        workspace, _ = assistant_db.read_markdown(workspace_source)
    subtasks = []
    parent_id = str(metadata.get("id") or source.stem)
    for child in assistant_db.iter_subtasks(root):
        if str(child.get("parent_workspace") or child.get("workspace")) != workspace_id or str(child.get("parent")) != parent_id:
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
        "workspace": workspace,
        "body": body,
        "tldr": str(metadata.get("tldr") or _summary(body)),
        "subtasks": subtasks,
    }


def _meeting_workspace(root: Path, source: Path) -> dict:
    if records.enabled(root):
        metadata, _ = assistant_db.read_markdown(source)
        return records.workspace(root, metadata.get('workspace'))
    try:
        directory = meeting_db.workspace(root, source.parent.parent.name)
        return assistant_db.read_markdown(naming.workspace_document_file(directory))[0]
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _meeting_record(root: Path, path: str, collection: str):
    source = _safe_markdown_path(root, path, collection)
    metadata, body = assistant_db.read_markdown(source)
    try:
        meeting_db.validate_owner(source, metadata)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return source, metadata, body


def _series_history(root: Path, source: Path):
    return [row for row in meeting_db.list_rows(root) if row.get("series") == source.stem
            and (records.enabled(root) or row["workspace"] == source.parent.parent.name)]


@router.get("/meeting")
def get_meeting(path: str, request: Request) -> dict:
    root = _require_root(request)
    source, metadata, body = _meeting_record(root, path, "meetings")
    overview, notes = meeting_db.sections(body)
    raw, series, warnings = None, None, []
    try:
        original = meeting_db.raw_path(root, source)
        if original.is_file():
            raw = {"path": str(original.relative_to(root)), "title": "Raw notes", "kind": "raw"}
    except ValueError as exc:
        warnings.append(f"Raw notes unavailable: {exc}")
    try:
        contents = list(meeting_db.iter_contents(root, source))
    except ValueError as exc:
        warnings.append(f"Related content unavailable: {exc}")
        contents = []
    if metadata.get("series"):
        try:
            parent, info, _ = meeting_db.find_series(root, str(metadata["series"]), source.parent.parent.name)
            series = {"id": parent.stem, "title": info.get("title") or parent.stem,
                      "path": str(parent.relative_to(root)), "meetings": _series_history(root, parent)}
        except ValueError as exc:
            warnings.append(f"Meeting series unavailable: {exc}")
    return {"path": str(source.relative_to(root)), "metadata": metadata,
            "workspace": _meeting_workspace(root, source), "body": body,
            "tldr": str(metadata.get("tldr") or meeting_db.summary(body)),
            "overview": overview, "notes": notes, "raw": raw, "contents": contents,
            "series": series, "warnings": warnings,
            **({k:v for k,v in assistant_v2.detail(root, path).items() if k in {"tree","root_path","root_kind","progress","embedded"}} if records.enabled(root) else {})}


@router.get("/meeting-series")
def get_meeting_series(path: str, request: Request) -> dict:
    root = _require_root(request)
    source, metadata, body = _meeting_record(root, path, "meeting-series")
    return {"path": str(source.relative_to(root)), "metadata": metadata, "body": body,
            "workspace": _meeting_workspace(root, source), "meetings": _series_history(root, source)}


def _safe_meeting_content(root: Path, path: str):
    try:
        return meeting_db.resolve_content(root, path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/meeting-content")
def get_meeting_content(path: str, request: Request) -> dict:
    root = _require_root(request)
    source, meeting, metadata = _safe_meeting_content(root, path)
    raw = metadata["kind"] == "raw"
    try:
        body = source.read_bytes().decode("utf-8") if raw else assistant_db.read_markdown(source)[1]
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"path": str(source.relative_to(root)), "metadata": metadata, "body": body,
            "workspace": _meeting_workspace(root, meeting), "meeting_path": str(meeting.relative_to(root)),
            "format": "text" if raw else "markdown"}


@router.get("/subtask")
def get_subtask(path: str, request: Request) -> dict:
    root = _require_root(request)
    if records.enabled(root):
        return assistant_v2.detail(root, path, 'subtasks')
    source = _safe_subtask_path(root, path)
    metadata, body = assistant_db.read_markdown(source)
    workspace_id = str(metadata.get("workspace") or source.parent.parent.name)
    workspace_source = naming.workspace_document_file(naming.workspaces_dir(root) / workspace_id)
    workspace: dict = {}
    if workspace_source.is_file():
        workspace, _ = assistant_db.read_markdown(workspace_source)
    return {
        "path": str(source.relative_to(root)),
        "metadata": metadata,
        "workspace": workspace,
        "body": body,
        "tldr": str(metadata.get("tldr") or _summary(body)),
    }


class AssistantMetadataBody(BaseModel):
    path: str
    field: str
    value: str | None
    expected: str | None


_metadata_lock = Lock()


@router.patch("/metadata")
def update_metadata(body: AssistantMetadataBody, request: Request) -> dict:
    """Update one visible property, retaining CLI lifecycle rules and fresh content."""
    root = _require_root(request)
    if records.enabled(root):
        fields = {'title','tldr','project','workspace','status','priority','due','recurrence','group','owner',
                  'scheduled','defer_until','waiting_on','follow_up_at','date','series'}
        if body.field not in fields:
            raise HTTPException(status_code=400, detail='This property cannot be edited')
        try:
            value = body.value.strip() or None if body.value is not None else None
            records.update(root, body.path, body.field, value, expected=body.expected)
            _, metadata, _ = records.resolve(root, body.path)
        except (OSError,ValueError) as exc:
            raise HTTPException(status_code=409 if 'changed elsewhere' in str(exc) else 400, detail=str(exc)) from exc
        if metadata.get('note_type') == 'meeting':
            return get_meeting(body.path, request)
        if metadata.get('note_type') == 'series':
            return get_meeting_series(body.path, request)
        return assistant_v2.detail(root, body.path)
    source = _safe_markdown_path(root, body.path)
    collection = source.parent.name
    fields = {"title", "tldr"}
    if collection in {"tasks", "subtasks"}:
        fields |= {"status", "priority", "due", "recurrence", "group", "owner",
                   "scheduled", "defer_until", "waiting_on", "follow_up_at"}
    elif collection == "meetings":
        fields |= {"date", "series"}
    elif collection != "meeting-series":
        raise HTTPException(status_code=400, detail="This document has no editable properties")
    if body.field not in fields:
        raise HTTPException(status_code=400, detail="This property cannot be edited")
    value = body.value.strip() if body.value is not None else None
    value = value or None
    try:
        if body.field == "title":
            meeting_db.validate_title(value)
        if value is not None and body.field in {"due", "scheduled", "defer_until", "follow_up_at", "date"}:
            meeting_db.validate_date(value)
        if value is not None and body.field == "recurrence" and value not in {"weekly", "monthly", "yearly"}:
            raise ValueError("Repeats must be weekly, monthly, yearly, or empty")
        with _metadata_lock:
            metadata, content = assistant_db.read_markdown(source)
            if metadata.get(body.field) != body.expected:
                raise HTTPException(status_code=409, detail="This property changed elsewhere. Reopen the document to load its latest value.")
            identifier = str(metadata.get("id") or source.stem)
            if collection in {"tasks", "subtasks", "meetings"}:
                finder, updater = {
                    "tasks": (assistant_db.find_task, assistant_db.update_task),
                    "subtasks": (assistant_db.find_subtask, assistant_db.update_subtask),
                    "meetings": (meeting_db.find_meeting, meeting_db.update_meeting),
                }[collection]
                # Never resolve a duplicate or mismatched ID to another document.
                if finder(root, identifier)[0].resolve() != source:
                    raise ValueError("Document ID does not match the selected path")
                updater(root, identifier, body.field, value)
            else:
                meeting_db.validate_owner(source, metadata)
                metadata.update({body.field: value, "updated": assistant_db.now_iso()})
                assistant_db.write_markdown(source, metadata, content)
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"tasks": get_task, "subtasks": get_subtask, "meetings": get_meeting,
            "meeting-series": get_meeting_series}[collection](body.path, request)


def _inside(target: Path, parent: Path) -> bool:
    try:
        return target == parent or parent in target.parents
    except OSError:
        return False


def _allowed_asset_roots(root: Path, task_path: Path) -> list[Path]:
    allowed = [root.resolve()]
    metadata, _ = assistant_db.read_markdown(task_path)
    workspace_id = str(metadata.get("workspace") or task_path.parent.parent.name)
    workspace_source = naming.workspace_document_file(naming.workspaces_dir(root) / workspace_id)
    if records.enabled(root) or workspace_source.is_file():
        workspace = records.workspace(root, metadata.get("workspace")) if records.enabled(root) else assistant_db.read_markdown(workspace_source)[0]
        for key in ("vault_path", "workspace_path"):
            raw = workspace.get(key)
            if isinstance(raw, str) and raw:
                allowed.append(Path(raw).expanduser().resolve())
    for row in paths.read_vault_registry().get("vaults") or []:
        raw = row.get("path")
        if isinstance(raw, str) and raw:
            allowed.append(Path(raw).expanduser().resolve())
    return allowed


@router.get("/asset")
def get_asset(task: str, src: str, request: Request):
    root = _require_root(request)
    if records.enabled(root):
        source = _safe_markdown_path(root, task)
        return assistant_v2.asset(root, task, src, _allowed_asset_roots(root, source))
    if len(Path(task).parts) > 4:
        task_path, _, metadata = _safe_meeting_content(root, task)
        if metadata["kind"] == "raw":
            raise HTTPException(status_code=400, detail="raw notes have no Markdown assets")
    else:
        task_path = _safe_markdown_path(root, task)
    parsed = urlparse(src)
    if parsed.scheme or parsed.netloc:
        raise HTTPException(status_code=400, detail="remote assets are loaded directly")
    raw = Path(src).expanduser()
    target = raw.resolve() if raw.is_absolute() else (task_path.parent / raw).resolve()
    if not any(_inside(target, allowed) for allowed in _allowed_asset_roots(root, task_path)):
        raise HTTPException(status_code=403, detail="asset is outside Assistant/workspace roots")
    if not target.is_file():
        raise HTTPException(status_code=404, detail="asset not found")
    return FileResponse(target)


@router.get("/note")
def get_note(path: str, request: Request) -> dict:
    return assistant_v2.detail(_require_root(request), path, 'notes')


@router.get("/link")
def get_link(document: str, src: str, request: Request):
    root = _require_root(request)
    source = _safe_markdown_path(root, document)
    return assistant_v2.asset(root, document, src, _allowed_asset_roots(root, source), link=True)


class AssistantRecordBody(BaseModel):
    type: str
    title: str
    project: str | None = None
    workspace: str | None = None
    parent: dict[str, str] | None = None


@router.post("/record")
def create_record(body: AssistantRecordBody, request: Request):
    root = _require_root(request)
    if not records.enabled(root):
        raise HTTPException(status_code=400, detail='Migrate Assistant first')
    try:
        if body.type == 'subtab':
            overrides = {field:getattr(body, field) for field in ('project','workspace') if field in body.model_fields_set}
            source = records.create_subtab(root, body.title, parent=body.parent, **overrides)
            return assistant_v2.detail(root, source.relative_to(root).as_posix())
        fields = {'project':body.project,'workspace':body.workspace,'parent':body.parent} if body.type != 'project' else {'status':'active'}
        if body.type == 'note':
            fields['note_type'] = 'subtab' if body.parent else 'plain'
        source = records.create(root, body.type, body.title, **fields)
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return assistant_v2.detail(root, source.relative_to(root).as_posix())
