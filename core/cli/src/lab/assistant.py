"""Filesystem contract for the client-owned global Assistant database.

The database is intentionally Markdown-first.  Project mappings live in
``projects/<id>/project.md``; tasks and their first-class subtasks are separate
Markdown files.  This module contains the small shared parser used by both the
CLI and Lab's read-only Assistant UI.
"""
from __future__ import annotations

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


AGENTS_TEMPLATE = """# Assistant task database

This directory is the client-owned global task database rendered by Lab's
Assistant tab. It is independent of every Lab workspace. Follow this contract
whenever the user asks you to add, update, complete, or save work here.

## Start every Assistant session

1. Read this file and `README.md`.
2. Run `lab assistant ls --status open` before creating duplicate work.
3. Resolve the request to an existing `projects/<id>/project.md` by its exact
   `workspace_path` and `project_path`. Never guess a mapping when two projects
   could match. Create a mapping with `lab assistant project add` only when the
   target is clear.
4. Keep source files, generated images, and other artifacts in their owning
   workspace/project. This database stores references and task context, not
   copies of project assets.

## Commands

```text
lab assistant path
lab assistant project ls
lab assistant project add <id> --name <name> --workspace <workspace-id> --path <absolute-project-path>
lab assistant add "Task title" --project <id> [--priority P0|P1|P2|P3] [--status inbox|ready|in_progress|waiting|blocked|ready_to_review]
lab assistant ls [--status open|<status>] [--priority P0] [--project <id>]
lab assistant show <task-id>
lab assistant set <task-id> <field> <value>
lab assistant done <task-id>
lab assistant subtask add "Subtask title" --parent <task-id> [--priority P0|P1|P2|P3] [--status inbox|ready|in_progress|waiting|blocked|ready_to_review]
lab assistant subtask ls [--parent <task-id>] [--status open|<status>]
lab assistant subtask show <subtask-id>
lab assistant subtask set <subtask-id> <field> <value>
lab assistant subtask done <subtask-id>
lab assistant meeting add "Meeting title" --project <id> [--date YYYY-MM-DD] [--attendee NAME]
lab assistant meeting ls [--project <id>]
lab assistant meeting show <meeting-id>
```

Use the commands for metadata changes. Edit the task Markdown body directly to
add context, decisions, checklists, links, or deliverables.

## Project files

Every `projects/<id>/project.md` has YAML frontmatter with:

- `id`, `name`, and `status`
- `workspace` and absolute `workspace_path`
- absolute `project_path`

The body may describe project-specific context that future agents should read.

## Task files

Each task lives at `projects/<project>/tasks/<task-id>.md`. Required metadata:
`id`, `title`, `status`, `priority`, `project`, `created`, and `updated`.
Optional metadata: `group`, `tldr`, `due`, `owner`, `waiting_on`, `waiting_since`, `follow_up_at`,
`last_follow_up_at`, `follow_up_channel`, `reviewer`, `review_requested_at`,
`executor`, `depends_on`, and `tags`. Create new child work as first-class
subtasks. Legacy Markdown checkbox items remain readable for older task files.

`group` is the internal project or workstream shown inside the mapped Lab
project. `tldr` is the concise summary rendered in task lists and modals.

Each first-class subtask lives at
`projects/<project>/subtasks/<subtask-id>.md`. Its required metadata is `id`,
`title`, `status`, `priority`, `project`, `parent`, `created`, and `updated`;
`due`, `owner`, `waiting_on`, `waiting_since`, `follow_up_at`,
`last_follow_up_at`, `follow_up_channel`, `reviewer`, `review_requested_at`,
`executor`, and `tags` are optional. Complete every checkbox and first-class
subtask before marking its parent task done.

Lifecycle:

- `inbox` — captured but not yet clarified
- `ready` — actionable and sufficiently specified
- `in_progress` — actively being worked
- `waiting` — waiting on time or an external response
- `blocked` — cannot progress; explain why under `# Blocker`
- `ready_to_review` — agent-produced work is ready for human review
- `done` — actually complete; set `completed` as well

P0 is urgent, P1 is important, P2 is normal, and P3 is someday/maybe.

## Meeting files

Meeting notes live at `projects/<project>/meetings/<meeting-id>.md`. Their
frontmatter includes `id`, `title`, `project`, `date`, `attendees`, `created`,
`updated`, and `tags`. Use one section each for `# Summary`, `# Highlights`,
`# Action items`, and `# Notes`; action-item checkboxes appear as individually
tracked follow-ups in Lab.

## Body conventions

Use ordinary Markdown. Prefer these sections when relevant:

```markdown
# Context
# Next actions
# Notes
# Output: Slack
# Output: Google Docs
# Generate content
# Result
```

Lab adds copy buttons to every level-one through level-three heading. Use a
single section for each independently copyable artifact. Reference images with
a path relative to the task file or an absolute path inside the mapped
workspace or project; Lab renders them without moving the asset.

Use `# Generate content` for a prepared email, announcement, or other manual
communication. Lab surfaces it from the task preview and offers formatted and
plain-text copy actions; sending remains a deliberate step outside Lab.

When work finishes, record the outcome and important artifact paths under
`# Result`, then run `lab assistant done <task-id>`. Do not mark a task done
merely because work stopped.
"""


README_TEMPLATE = """# Assistant

This is the client-owned global database for Lab's Assistant tab.

- `AGENTS.md` is the operational contract for terminal agents.
- `projects/<id>/project.md` maps an Assistant project to a Lab workspace and
  an absolute project path.
- `projects/<id>/tasks/*.md` contains one task per Markdown file.
- `projects/<id>/subtasks/*.md` contains one first-class subtask per Markdown file.
- `projects/<id>/meetings/*.md` contains one meeting note per Markdown file.
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
    return metadata, text[end + 5:]


def write_markdown(path: Path, metadata: dict[str, Any], body: str) -> None:
    lines = ["---"]
    for key, value in metadata.items():
        lines.append(f"{key}: {json.dumps(value, ensure_ascii=False)}")
    lines.extend(["---", "", body.rstrip(), ""])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def initialize(root: Path | None = None) -> Path:
    target = (root or configured_root()).expanduser().resolve()
    (target / "projects").mkdir(parents=True, exist_ok=True)
    if not (target / "AGENTS.md").exists():
        (target / "AGENTS.md").write_text(AGENTS_TEMPLATE, encoding="utf-8")
    if not (target / "README.md").exists():
        (target / "README.md").write_text(README_TEMPLATE, encoding="utf-8")
    return target


def project_dir(root: Path, project_id: str) -> Path:
    return root / "projects" / validate_id(project_id, label="project id")


def iter_projects(root: Path) -> Iterator[dict[str, Any]]:
    base = root / "projects"
    if not base.is_dir():
        return
    for child in sorted(base.iterdir()):
        source = child / "project.md"
        if not child.is_dir() or not source.is_file():
            continue
        metadata, body = read_markdown(source)
        project_id = str(metadata.get("id") or child.name)
        yield {
            **metadata,
            "id": project_id,
            "name": str(metadata.get("name") or project_id),
            "status": str(metadata.get("status") or "active"),
            "body": body,
            "path": str(source.relative_to(root)),
        }


def iter_tasks(root: Path, projects: list[dict[str, Any]] | None = None) -> Iterator[dict[str, Any]]:
    project_rows = projects if projects is not None else list(iter_projects(root))
    by_id = {str(row["id"]): row for row in project_rows}
    first_class_by_parent: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for subtask in iter_subtasks(root, project_rows):
        key = (str(subtask["project"]), str(subtask["parent"]))
        first_class_by_parent.setdefault(key, []).append(subtask)
    for project_id, project in by_id.items():
        task_dir = root / "projects" / project_id / "tasks"
        if not task_dir.is_dir():
            continue
        for source in sorted(task_dir.glob("*.md")):
            metadata, body = read_markdown(source)
            task_id = str(metadata.get("id") or source.stem)
            legacy_subtasks = extract_subtasks(body)
            first_class_subtasks = first_class_by_parent.get((project_id, task_id), [])
            subtasks = [*legacy_subtasks, *first_class_subtasks]
            yield {
                **metadata,
                "id": task_id,
                "title": str(metadata.get("title") or task_id),
                "status": str(metadata.get("status") or "inbox"),
                "priority": str(metadata.get("priority") or "P2"),
                "project": project_id,
                "project_name": project.get("name") or project_id,
                "workspace": project.get("workspace"),
                "workspace_path": project.get("workspace_path"),
                "project_path": project.get("project_path"),
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
    projects: list[dict[str, Any]] | None = None,
) -> Iterator[dict[str, Any]]:
    """Yield first-class subtask documents with their project routing context."""
    project_rows = projects if projects is not None else list(iter_projects(root))
    by_id = {str(row["id"]): row for row in project_rows}
    for project_id, project in by_id.items():
        subtask_dir = root / "projects" / project_id / "subtasks"
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
                "project": project_id,
                "parent": str(metadata.get("parent") or ""),
                "project_name": project.get("name") or project_id,
                "workspace": project.get("workspace"),
                "workspace_path": project.get("workspace_path"),
                "project_path": project.get("project_path"),
                "body": body,
                "done": status == "done",
                "document_backed": True,
                "path": str(source.relative_to(root)),
                "mtime": source.stat().st_mtime,
            }


def iter_meetings(root: Path, projects: list[dict[str, Any]] | None = None) -> Iterator[dict[str, Any]]:
    project_rows = projects if projects is not None else list(iter_projects(root))
    by_id = {str(row["id"]): row for row in project_rows}
    for project_id, project in by_id.items():
        meeting_dir = root / "projects" / project_id / "meetings"
        if not meeting_dir.is_dir():
            continue
        for source in sorted(meeting_dir.glob("*.md")):
            metadata, body = read_markdown(source)
            meeting_id = str(metadata.get("id") or source.stem)
            actions = extract_subtasks(body)
            yield {
                **metadata,
                "id": meeting_id,
                "title": str(metadata.get("title") or meeting_id),
                "project": project_id,
                "project_name": project.get("name") or project_id,
                "workspace": project.get("workspace"),
                "workspace_path": project.get("workspace_path"),
                "project_path": project.get("project_path"),
                "body": body,
                "action_items": actions,
                "action_items_done": sum(1 for item in actions if item["status"] == "done"),
                "action_items_total": len(actions),
                "path": str(source.relative_to(root)),
                "mtime": source.stat().st_mtime,
            }


def find_task(root: Path, task_id: str) -> tuple[Path, dict[str, Any], str]:
    matches: list[tuple[Path, dict[str, Any], str]] = []
    for source in (root / "projects").glob("*/tasks/*.md"):
        metadata, body = read_markdown(source)
        if str(metadata.get("id") or source.stem) == task_id:
            matches.append((source, metadata, body))
    if not matches:
        raise ValueError(f"task {task_id!r} not found")
    if len(matches) > 1:
        raise ValueError(f"task id {task_id!r} is not unique")
    return matches[0]


def find_subtask(root: Path, subtask_id: str) -> tuple[Path, dict[str, Any], str]:
    matches: list[tuple[Path, dict[str, Any], str]] = []
    for source in (root / "projects").glob("*/subtasks/*.md"):
        metadata, body = read_markdown(source)
        if str(metadata.get("id") or source.stem) == subtask_id:
            matches.append((source, metadata, body))
    if not matches:
        raise ValueError(f"subtask {subtask_id!r} not found")
    if len(matches) > 1:
        raise ValueError(f"subtask id {subtask_id!r} is not unique")
    return matches[0]


def find_meeting(root: Path, meeting_id: str) -> tuple[Path, dict[str, Any], str]:
    matches: list[tuple[Path, dict[str, Any], str]] = []
    for source in (root / "projects").glob("*/meetings/*.md"):
        metadata, body = read_markdown(source)
        if str(metadata.get("id") or source.stem) == meeting_id:
            matches.append((source, metadata, body))
    if not matches:
        raise ValueError(f"meeting {meeting_id!r} not found")
    if len(matches) > 1:
        raise ValueError(f"meeting id {meeting_id!r} is not unique")
    return matches[0]


def create_project(
    root: Path,
    project_id: str,
    *,
    name: str,
    workspace: str,
    workspace_path: Path,
    project_path: Path,
) -> Path:
    pdir = project_dir(root, project_id)
    source = pdir / "project.md"
    if source.exists():
        raise ValueError(f"Assistant project {project_id!r} already exists")
    timestamp = now_iso()
    write_markdown(source, {
        "id": project_id,
        "name": name,
        "status": "active",
        "workspace": workspace,
        "workspace_path": str(workspace_path.expanduser().resolve()),
        "project_path": str(project_path.expanduser().resolve()),
        "created": timestamp,
        "updated": timestamp,
    }, f"# {name}\n\nProject context and routing notes.\n")
    (pdir / "tasks").mkdir(exist_ok=True)
    (pdir / "subtasks").mkdir(exist_ok=True)
    (pdir / "meetings").mkdir(exist_ok=True)
    return source


def create_task(
    root: Path,
    title: str,
    *,
    project_id: str,
    priority: str = "P2",
    status: str = "inbox",
    due: str | None = None,
    owner: str | None = None,
    tags: list[str] | None = None,
) -> Path:
    if priority not in PRIORITIES:
        raise ValueError(f"priority must be one of: {', '.join(PRIORITIES)}")
    if status not in STATUSES or status == "done":
        raise ValueError(f"new task status must be one of: {', '.join(STATUSES[:-1])}")
    pdir = project_dir(root, project_id)
    if not (pdir / "project.md").is_file():
        raise ValueError(f"Assistant project {project_id!r} not found")
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
        "project": project_id,
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
        "# Context\n\nDescribe why this task exists.\n\n# Next actions\n\n"
        "Add document-backed subtasks with `lab assistant subtask add`.\n",
    )
    return source


def create_subtask(
    root: Path,
    title: str,
    *,
    parent: str,
    priority: str = "P2",
    status: str = "inbox",
    due: str | None = None,
    owner: str | None = None,
    tags: list[str] | None = None,
) -> Path:
    if priority not in PRIORITIES:
        raise ValueError(f"priority must be one of: {', '.join(PRIORITIES)}")
    if status not in STATUSES or status == "done":
        raise ValueError(f"new subtask status must be one of: {', '.join(STATUSES[:-1])}")
    parent_source, parent_metadata, _parent_body = find_task(root, parent)
    project_id = str(parent_metadata.get("project") or parent_source.parent.parent.name)
    pdir = project_dir(root, project_id)
    if not (pdir / "project.md").is_file():
        raise ValueError(f"Assistant project {project_id!r} not found")
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
        "project": project_id,
        "parent": parent,
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
        "# Context\n\nDescribe the concrete outcome for this subtask.\n\n# Result\n",
    )
    return source


def create_meeting(
    root: Path,
    title: str,
    *,
    project_id: str,
    date: str | None = None,
    attendees: list[str] | None = None,
    tags: list[str] | None = None,
) -> Path:
    pdir = project_dir(root, project_id)
    if not (pdir / "project.md").is_file():
        raise ValueError(f"Assistant project {project_id!r} not found")
    meeting_date = date or datetime.now().astimezone().date().isoformat()
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    base_id = f"{stamp}-{slugify(title)}"
    meeting_id = base_id
    meeting_dir = pdir / "meetings"
    source = meeting_dir / f"{meeting_id}.md"
    suffix = 2
    while source.exists():
        meeting_id = f"{base_id}-{suffix}"
        source = meeting_dir / f"{meeting_id}.md"
        suffix += 1
    timestamp = now_iso()
    metadata: dict[str, Any] = {
        "id": meeting_id,
        "title": title,
        "project": project_id,
        "date": meeting_date,
        "attendees": attendees or [],
        "created": timestamp,
        "updated": timestamp,
        "tags": tags or [],
    }
    write_markdown(
        source,
        metadata,
        "# Summary\n\nCapture the decision or outcome in a few sentences.\n\n"
        "# Highlights\n\n- Add the most useful discussion points.\n\n"
        "# Action items\n\n## For me\n\n- [ ] Add a personal follow-up.\n\n"
        "## Other action items\n\n- [ ] Add an owner and follow-up.\n\n"
        "# Notes\n\nAdd supporting notes, links, and context.\n",
    )
    return source


def update_task(root: Path, task_id: str, field: str, value: Any) -> Path:
    source, metadata, body = find_task(root, task_id)
    if field == "status" and value not in STATUSES:
        raise ValueError(f"status must be one of: {', '.join(STATUSES)}")
    if field == "priority" and value not in PRIORITIES:
        raise ValueError(f"priority must be one of: {', '.join(PRIORITIES)}")
    if field == "status" and value == "done":
        legacy_incomplete = [item for item in extract_subtasks(body) if item["status"] != "done"]
        project_id = str(metadata.get("project") or source.parent.parent.name)
        first_class_incomplete = [
            item for item in iter_subtasks(root)
            if item["project"] == project_id
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
