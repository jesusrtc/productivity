"""Filesystem contract for the client-owned global Assistant database.

The database is intentionally Markdown-first.  Workspace mappings live in
``workspaces/<id>/workspace.md``; tasks and their first-class subtasks are separate
Markdown files.  This module contains the small shared parser used by both the
CLI and Lab's read-only Assistant UI.
"""
from __future__ import annotations

from lab import assistant_records as records, naming, assistant_meetings as meeting_db

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from lab import paths


STATUSES = (
    "inbox",
    "ready",
    "in_progress",
    "waiting",
    "blocked",
    "ready_to_review",
    "done",
)
PRIORITIES = ("P0", "P1", "P2", "P3")
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
_SLUG_RE = re.compile(r"[^a-z0-9]+")
_CHECKBOX_RE = re.compile(r"^\s*[-*]\s+\[([ xX])\]\s+(.+?)\s*$")


AGENTS_TEMPLATE = """# Assistant database

This database belongs to the client. The client decides the content, structure,
headings, language, and formatting of tasks, notes, and tabs. Lab provides
storage and rendering; new bodies are empty. Follow the client's instructions
and preserve existing content. No document sections or writing workflow are
required by Lab.

Read README.md and inspect the manifest before editing. Use `lab assistant ls
--status open` to find existing work, and `lab assistant workspace ls` and
`lab assistant project ls` to resolve existing references.

Read `lab migrations assistant-subtabs` for the current technical storage
contract: one Markdown file per task or note with embedded tabs. Legacy
workspace-folder and separate-record databases remain readable; migrate only
when authorized. `lab context tasks` and `lab context meetings` describe the
available metadata and commands, not required document content.

Agents may edit Markdown and frontmatter directly. CLI commands are optional
conveniences for IDs and validation. Re-read before a targeted edit; preserve
IDs, relationships, unknown metadata, siblings, and original captures.
Client instructions and README.md must not be overwritten by migrations.
"""


README_TEMPLATE = """# Assistant

This is the client-owned global database for Lab's Assistant tab.

- `AGENTS.md` is the operational contract for terminal agents.
- `workspaces/<id>/workspace.md` maps an Assistant workspace to a Lab vault and
  an absolute workspace path.
- `workspaces/<id>/tasks/*.md` contains one task per Markdown file.
- `workspaces/<id>/subtasks/*.md` contains one first-class subtask per Markdown file.
- `workspaces/<id>/meetings/*.md` contains one meeting note per Markdown file.
- `.lab/` contains Lab-managed terminal/runtime state and may be ignored by
  version control.

The directory is selected at Lab startup with `LAB_ASSISTANT_HOME` in the Lab
client checkout's `.env`, or as a process environment override.
"""


def configured_root() -> Path:
    root = paths.assistant_root()
    if root is None:
        raise ValueError(
            "Assistant database is not configured; set LAB_ASSISTANT_HOME in the Lab client .env"
        )
    return root


def now_iso() -> str:
    return datetime.now(tz=timezone.utc).astimezone().isoformat(timespec="seconds")


def slugify(value: str, *, max_len: int = 48) -> str:
    return _SLUG_RE.sub("-", value.lower()).strip("-")[:max_len] or "task"


def validate_id(value: str, *, label: str = "id") -> str:
    if not _ID_RE.fullmatch(value):
        raise ValueError(f"{label} must match [a-z0-9][a-z0-9_-]*")
    return value


def _decode_scalar(value: str) -> Any:
    text = value.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def read_markdown(path: Path) -> tuple[dict[str, Any], str]:
    if '#tab=' in str(path):
        return records.read_document(path)
    data = path.read_bytes()
    if data.startswith(b'---') and re.search(rb'^schema:\s*2\s*$', data.split(b'---', 2)[1], re.M):
        return records.read_document(path)
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end < 0:
        return {}, text
    metadata: dict[str, Any] = {}
    for raw in text[4:end].splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        key, sep, value = raw.partition(":")
        if not sep or not key.strip():
            continue
        metadata[key.strip()] = _decode_scalar(value)
    if "project" in metadata or "project_path" in metadata:
        metadata = naming.legacy_fields(metadata)
    return metadata, text[end + 5:]


def write_markdown(path: Path, metadata: dict[str, Any], body: str) -> None:
    if metadata.get('schema') == 2:
        return records.write_document(path, metadata, body)
    lines = ["---"]
    for key, value in metadata.items():
        lines.append(f"{key}: {json.dumps(value, ensure_ascii=False)}")
    lines.extend(["---", "", body.rstrip(), ""])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def initialize(root: Path | None = None) -> Path:
    target = (root or configured_root()).expanduser().resolve()
    if records.enabled(target):
        for folder in ('tasks', 'notes', 'projects'):
            (target / folder).mkdir(exist_ok=True)
        return target
    (naming.workspaces_dir(target)).mkdir(parents=True, exist_ok=True)
    if not (target / "AGENTS.md").exists():
        (target / "AGENTS.md").write_text(AGENTS_TEMPLATE, encoding="utf-8")
    if not (target / "README.md").exists():
        (target / "README.md").write_text(README_TEMPLATE, encoding="utf-8")
    return target


def workspace_dir(root: Path, workspace_id: str) -> Path:
    return naming.workspaces_dir(root) / validate_id(workspace_id, label="workspace id")


def iter_workspaces(root: Path) -> Iterator[dict[str, Any]]:
    if records.enabled(root):
        yield from records.workspaces(root)
        return
    base = naming.workspaces_dir(root)
    if not base.is_dir():
        return
    for child in sorted(base.iterdir()):
        source = naming.workspace_document_file(child)
        if not child.is_dir() or not source.is_file():
            continue
        metadata, body = read_markdown(source)
        workspace_id = str(metadata.get("id") or child.name)
        yield {
            **metadata,
            "id": workspace_id,
            "name": str(metadata.get("name") or workspace_id),
            "status": str(metadata.get("status") or "active"),
            "body": body,
            "path": str(source.relative_to(root)),
        }


def iter_tasks(root: Path, workspaces: list[dict[str, Any]] | None = None) -> Iterator[dict[str, Any]]:
    if records.enabled(root):
        yield from records.task_rows(root)
        return
    workspace_rows = workspaces if workspaces is not None else list(iter_workspaces(root))
    by_id = {str(row["id"]): row for row in workspace_rows}
    first_class_by_parent: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for subtask in iter_subtasks(root, workspace_rows):
        key = (str(subtask.get("parent_workspace") or subtask["workspace"]), str(subtask["parent"]))
        first_class_by_parent.setdefault(key, []).append(subtask)
    for workspace_id, workspace in by_id.items():
        task_dir = naming.workspaces_dir(root) / workspace_id / "tasks"
        if not task_dir.is_dir():
            continue
        for source in sorted(task_dir.glob("*.md")):
            metadata, body = read_markdown(source)
            task_id = str(metadata.get("id") or source.stem)
            legacy_subtasks = extract_subtasks(body)
            first_class_subtasks = first_class_by_parent.get((workspace_id, task_id), [])
            subtasks = [*legacy_subtasks, *first_class_subtasks]
            yield {
                **metadata,
                "id": task_id,
                "title": str(metadata.get("title") or task_id),
                "status": str(metadata.get("status") or "inbox"),
                "priority": str(metadata.get("priority") or "P2"),
                "workspace": workspace_id,
                "workspace_name": workspace.get("name") or workspace_id,
                "vault": workspace.get("vault"),
                "vault_path": workspace.get("vault_path"),
                "workspace_path": workspace.get("workspace_path"),
                "body": body,
                "subtasks": subtasks,
                "legacy_subtasks": legacy_subtasks,
                "first_class_subtasks": first_class_subtasks,
                "subtasks_done": sum(1 for item in subtasks if item["status"] == "done"),
                "subtasks_total": len(subtasks),
                "path": str(source.relative_to(root)),
                "mtime": source.stat().st_mtime,
            }


def extract_subtasks(body: str) -> list[dict[str, Any]]:
    """Return legacy Markdown checklist items as the task's visible subtasks."""
    items: list[dict[str, Any]] = []
    for raw in body.splitlines():
        match = _CHECKBOX_RE.match(raw)
        if not match:
            continue
        done = match.group(1).lower() == "x"
        items.append({
            "title": match.group(2).strip(),
            "status": "done" if done else "open",
            "done": done,
        })
    return items


def iter_subtasks(
    root: Path,
    workspaces: list[dict[str, Any]] | None = None,
) -> Iterator[dict[str, Any]]:
    """Yield first-class subtask documents with their workspace routing context."""
    if records.enabled(root):
        yield from records.task_rows(root, children_only=True)
        return
    workspace_rows = workspaces if workspaces is not None else list(iter_workspaces(root))
    by_id = {str(row["id"]): row for row in workspace_rows}
    for workspace_id, workspace in by_id.items():
        subtask_dir = naming.workspaces_dir(root) / workspace_id / "subtasks"
        if not subtask_dir.is_dir():
            continue
        for source in sorted(subtask_dir.glob("*.md")):
            metadata, body = read_markdown(source)
            subtask_id = str(metadata.get("id") or source.stem)
            status = str(metadata.get("status") or "inbox")
            yield {
                **metadata,
                "id": subtask_id,
                "title": str(metadata.get("title") or subtask_id),
                "status": status,
                "priority": str(metadata.get("priority") or "P2"),
                "workspace": workspace_id,
                "parent": str(metadata.get("parent") or ""),
                "workspace_name": workspace.get("name") or workspace_id,
                "vault": workspace.get("vault"),
                "vault_path": workspace.get("vault_path"),
                "workspace_path": workspace.get("workspace_path"),
                "body": body,
                "done": status == "done",
                "document_backed": True,
                "path": str(source.relative_to(root)),
                "mtime": source.stat().st_mtime,
            }


def find_task(root: Path, task_id: str) -> tuple[Path, dict[str, Any], str]:
    if records.enabled(root):
        return records.resolve(root, task_id, 'tasks')
    matches: list[tuple[Path, dict[str, Any], str]] = []
    for source in (naming.workspaces_dir(root)).glob("*/tasks/*.md"):
        metadata, body = read_markdown(source)
        if str(metadata.get("id") or source.stem) == task_id:
            matches.append((source, metadata, body))
    if not matches:
        raise ValueError(f"task {task_id!r} not found")
    if len(matches) > 1:
        raise ValueError(f"task id {task_id!r} is not unique")
    return matches[0]


def find_subtask(root: Path, subtask_id: str) -> tuple[Path, dict[str, Any], str]:
    if records.enabled(root):
        return records.resolve(root, subtask_id, 'tasks')
    matches: list[tuple[Path, dict[str, Any], str]] = []
    for source in (naming.workspaces_dir(root)).glob("*/subtasks/*.md"):
        metadata, body = read_markdown(source)
        if str(metadata.get("id") or source.stem) == subtask_id:
            matches.append((source, metadata, body))
    if not matches:
        raise ValueError(f"subtask {subtask_id!r} not found")
    if len(matches) > 1:
        raise ValueError(f"subtask id {subtask_id!r} is not unique")
    return matches[0]


def create_workspace(
    root: Path,
    workspace_id: str,
    *,
    name: str,
    vault: str,
    vault_path: Path,
    workspace_path: Path,
) -> Path:
    if records.enabled(root):
        return records.add_workspace(root, workspace_id, name=name, status='active', vault=vault,
                                     vault_path=vault_path.expanduser().resolve(),
                                     workspace_path=workspace_path.expanduser().resolve(), body='')
    pdir = workspace_dir(root, workspace_id)
    source = pdir / "workspace.md"
    if source.exists():
        raise ValueError(f"Assistant workspace {workspace_id!r} already exists")
    timestamp = now_iso()
    write_markdown(source, {
        "id": workspace_id,
        "name": name,
        "status": "active",
        "vault": vault,
        "vault_path": str(vault_path.expanduser().resolve()),
        "workspace_path": str(workspace_path.expanduser().resolve()),
        "created": timestamp,
        "updated": timestamp,
    }, f"# {name}\n\nWorkspace context and routing notes.\n")
    (pdir / "tasks").mkdir(exist_ok=True)
    (pdir / "subtasks").mkdir(exist_ok=True)
    (pdir / "meetings").mkdir(exist_ok=True)
    return source


def create_task(
    root: Path,
    title: str,
    *,
    workspace_id: str | None = None,
    project_id: str | None = None,
    priority: str = "P2",
    status: str = "inbox",
    due: str | None = None,
    owner: str | None = None,
    tags: list[str] | None = None,
) -> Path:
    if records.enabled(root):
        return records.create(root, 'task', title, workspace=workspace_id, project=project_id,
                              priority=priority, status=status, due=due, owner=owner, tags=tags or [],
                              body='')
    if not workspace_id:
        raise ValueError('Legacy databases require --workspace; run lab assistant migrate --apply')
    if priority not in PRIORITIES:
        raise ValueError(f"priority must be one of: {', '.join(PRIORITIES)}")
    if status not in STATUSES or status == "done":
        raise ValueError(f"new task status must be one of: {', '.join(STATUSES[:-1])}")
    pdir = workspace_dir(root, workspace_id)
    if not naming.workspace_document_file(pdir).is_file():
        raise ValueError(f"Assistant workspace {workspace_id!r} not found")
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    base_id = f"{stamp}-{slugify(title)}"
    task_id = base_id
    task_dir = pdir / "tasks"
    source = task_dir / f"{task_id}.md"
    suffix = 2
    while source.exists():
        task_id = f"{base_id}-{suffix}"
        source = task_dir / f"{task_id}.md"
        suffix += 1
    timestamp = now_iso()
    metadata: dict[str, Any] = {
        "id": task_id,
        "title": title,
        "status": status,
        "priority": priority,
        "workspace": workspace_id,
        "created": timestamp,
        "updated": timestamp,
        "due": due,
        "owner": owner,
        "depends_on": [],
        "tags": tags or [],
    }
    if status == "ready_to_review":
        metadata["review_requested_at"] = timestamp
    write_markdown(
        source,
        metadata,
        "",
    )
    return source


def create_subtask(
    root: Path,
    title: str,
    *,
    parent: str,
    workspace: str | None = None,
    priority: str = "P2",
    status: str = "inbox",
    due: str | None = None,
    owner: str | None = None,
    tags: list[str] | None = None,
) -> Path:
    if records.enabled(root):
        _, parent_metadata, _ = records.resolve(root, parent, 'tasks')
        return records.create(root, 'task', title, parent={'type':'task','id':parent_metadata['id']},
                              workspace=workspace or parent_metadata.get('workspace'),
                              project=parent_metadata.get('project'), priority=priority, status=status,
                              due=due, owner=owner, tags=tags or [], body='')
    if priority not in PRIORITIES:
        raise ValueError(f"priority must be one of: {', '.join(PRIORITIES)}")
    if status not in STATUSES or status == "done":
        raise ValueError(f"new subtask status must be one of: {', '.join(STATUSES[:-1])}")
    parent_source, parent_metadata, _parent_body = find_task(root, parent)
    parent_workspace = str(parent_metadata.get("workspace") or parent_source.parent.parent.name)
    workspace_id = workspace or parent_workspace
    pdir = workspace_dir(root, workspace_id)
    if not naming.workspace_document_file(pdir).is_file():
        raise ValueError(f"Assistant workspace {workspace_id!r} not found")
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    base_id = f"{stamp}-{slugify(title)}"
    subtask_id = base_id
    subtask_dir = pdir / "subtasks"
    source = subtask_dir / f"{subtask_id}.md"
    suffix = 2
    while source.exists():
        subtask_id = f"{base_id}-{suffix}"
        source = subtask_dir / f"{subtask_id}.md"
        suffix += 1
    timestamp = now_iso()
    metadata: dict[str, Any] = {
        "id": subtask_id,
        "title": title,
        "status": status,
        "priority": priority,
        "workspace": workspace_id,
        "parent": parent,
        "parent_workspace": parent_workspace,
        "created": timestamp,
        "updated": timestamp,
        "due": due,
        "owner": owner,
        "tags": tags or [],
    }
    if status == "ready_to_review":
        metadata["review_requested_at"] = timestamp
    write_markdown(
        source,
        metadata,
        "",
    )
    return source


def update_task(root: Path, task_id: str, field: str, value: Any) -> Path:
    if records.enabled(root):
        return records.update(root, task_id, field, value, collection='tasks')
    source, metadata, body = find_task(root, task_id)
    if field == "status" and value not in STATUSES:
        raise ValueError(f"status must be one of: {', '.join(STATUSES)}")
    if field == "priority" and value not in PRIORITIES:
        raise ValueError(f"priority must be one of: {', '.join(PRIORITIES)}")
    if field == "status" and value == "done":
        legacy_incomplete = [item for item in extract_subtasks(body) if item["status"] != "done"]
        workspace_id = str(metadata.get("workspace") or source.parent.parent.name)
        first_class_incomplete = [
            item for item in iter_subtasks(root)
            if (item.get("parent_workspace") or item["workspace"]) == workspace_id
            and item["parent"] == task_id
            and item["status"] != "done"
        ]
        incomplete = [*legacy_incomplete, *first_class_incomplete]
        if incomplete:
            suffix = "s" if len(incomplete) != 1 else ""
            raise ValueError(
                f"task has {len(incomplete)} incomplete subtask{suffix}; "
                "complete every checkbox and first-class subtask before marking it done"
            )
    metadata[field] = value
    metadata["updated"] = now_iso()
    if field == "status":
        if value == "done":
            metadata["completed"] = now_iso()
        else:
            metadata.pop("completed", None)
        if value == "waiting" and not metadata.get("waiting_since"):
            metadata["waiting_since"] = now_iso()
        if value == "ready_to_review" and not metadata.get("review_requested_at"):
            metadata["review_requested_at"] = now_iso()
    write_markdown(source, metadata, body)
    return source


def update_subtask(root: Path, subtask_id: str, field: str, value: Any) -> Path:
    if records.enabled(root):
        return records.update(root, subtask_id, field, value, collection='tasks')
    source, metadata, body = find_subtask(root, subtask_id)
    if field == "status" and value not in STATUSES:
        raise ValueError(f"status must be one of: {', '.join(STATUSES)}")
    if field == "priority" and value not in PRIORITIES:
        raise ValueError(f"priority must be one of: {', '.join(PRIORITIES)}")
    metadata[field] = value
    metadata["updated"] = now_iso()
    if field == "status":
        if value == "done":
            metadata["completed"] = now_iso()
        else:
            metadata.pop("completed", None)
        if value == "waiting" and not metadata.get("waiting_since"):
            metadata["waiting_since"] = now_iso()
        if value == "ready_to_review" and not metadata.get("review_requested_at"):
            metadata["review_requested_at"] = now_iso()
    write_markdown(source, metadata, body)
    return source


def create_meeting(*args, **kwargs):
    return meeting_db.create_meeting(*args, **kwargs)


def find_meeting(*args, **kwargs):
    return meeting_db.find_meeting(*args, **kwargs)


def iter_meetings(*args, **kwargs):
    return meeting_db.iter_meetings(*args, **kwargs)


def create_meeting_series(*args, **kwargs):
    return meeting_db.create_series(*args, **kwargs)


def find_meeting_series(*args, **kwargs):
    return meeting_db.find_series(*args, **kwargs)


def iter_meeting_series(*args, **kwargs):
    return meeting_db.iter_series(*args, **kwargs)


def meeting_list_rows(*args, **kwargs):
    return meeting_db.list_rows(*args, **kwargs)


def meeting_sections(*args, **kwargs):
    return meeting_db.sections(*args, **kwargs)


def meeting_summary(*args, **kwargs):
    return meeting_db.summary(*args, **kwargs)


def meeting_actions(*args, **kwargs):
    return meeting_db.actions(*args, **kwargs)


def meeting_raw_path(*args, **kwargs):
    return meeting_db.raw_path(*args, **kwargs)


def add_meeting_raw(*args, **kwargs):
    return meeting_db.add_raw(*args, **kwargs)


def create_meeting_content(*args, **kwargs):
    return meeting_db.create_content(*args, **kwargs)


def iter_meeting_contents(*args, **kwargs):
    return meeting_db.iter_contents(*args, **kwargs)


def resolve_meeting_content(*args, **kwargs):
    return meeting_db.resolve_content(*args, **kwargs)


def update_meeting(*args, **kwargs):
    return meeting_db.update_meeting(*args, **kwargs)
