from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lab import paths, storage


Index = dict[str, Any]


def _project_task_summary(tasks_doc: dict[str, Any]) -> dict[str, Any]:
    counts = {"todo": 0, "in_progress": 0, "blocked": 0, "done": 0}
    earliest_due: str | None = None
    for t in tasks_doc.get("tasks", []):
        s = t.get("status")
        if s in counts:
            counts[s] += 1
        due = t.get("due")
        if due and (earliest_due is None or due < earliest_due):
            earliest_due = due
    open_count = counts["todo"] + counts["in_progress"] + counts["blocked"]
    return {
        "task_counts": counts,
        "open_task_count": open_count,
        "blocked_task_count": counts["blocked"],
        "earliest_task_due": earliest_due,
    }


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).astimezone().isoformat(timespec="seconds")


def build_index(root: Path) -> Index:
    """Walk knowledge/projects/ and return the cached index shape.

    Projects are sorted by id. Tasks are emitted flat (one per row) with
    `project_id`, `task_id`, and path fields for cheap filtering.
    """
    projects_root = root / "knowledge" / "projects"
    project_rows: list[dict[str, Any]] = []
    task_rows: list[dict[str, Any]] = []

    if projects_root.is_dir():
        for child in sorted(projects_root.iterdir()):
            pjson = child / "project.json"
            tjson = child / "tasks.json"
            if not pjson.is_file():
                continue

            pdata = storage.read_json(pjson)
            tasks_doc = storage.read_json(tjson) if tjson.is_file() else {"tasks": []}
            summary = _project_task_summary(tasks_doc)

            project_rows.append({
                "id": pdata.get("id", child.name),
                "name": pdata.get("name", child.name),
                "description": pdata.get("description", ""),
                "status": pdata.get("status", "active"),
                "tags": list(pdata.get("tags") or []),
                "labels": list(pdata.get("labels") or []),
                "priority": pdata.get("priority"),
                "loe": pdata.get("loe"),
                "due": pdata.get("due"),
                "created": pdata.get("created"),
                "updated": pdata.get("updated"),
                "hold": pdata.get("hold") or None,
                "path": f"knowledge/projects/{child.name}",
                **summary,
            })

            for t in tasks_doc.get("tasks", []):
                task_rows.append({
                    "project_id": child.name,
                    "task_id": t["id"],
                    "title": t.get("title", ""),
                    "status": t.get("status"),
                    "priority": t.get("priority"),
                    "loe": t.get("loe"),
                    "due": t.get("due"),
                    "tags": list(t.get("tags") or []),
                    "labels": list(t.get("labels") or []),
                    "blocker": t.get("blocker"),
                    "notes_file": t.get("notes_file"),
                    "created": t.get("created"),
                    "updated": t.get("updated"),
                    "closed_at": t.get("closed_at"),
                    "path": f"knowledge/projects/{child.name}/tasks.json#{t['id']}",
                })

    # Include the __self__ pseudo-project so its tasks surface in global
    # listings (due-soon, /api/tasks). Kept out of `projects` rows to
    # avoid it appearing in project pickers.
    self_tasks = root / "knowledge" / ".self-tasks.json"
    if self_tasks.is_file():
        doc = storage.read_json(self_tasks)
        for t in doc.get("tasks", []):
            task_rows.append({
                "project_id": paths.SELF_PROJECT_ID,
                "task_id": t["id"],
                "title": t.get("title", ""),
                "status": t.get("status"),
                "priority": t.get("priority"),
                "loe": t.get("loe"),
                "due": t.get("due"),
                "tags": list(t.get("tags") or []),
                "labels": list(t.get("labels") or []),
                "blocker": t.get("blocker"),
                "notes_file": t.get("notes_file"),
                "created": t.get("created"),
                "updated": t.get("updated"),
                "closed_at": t.get("closed_at"),
                "path": f"knowledge/.self-tasks.json#{t['id']}",
            })

    return {
        "generated_at": _now_iso(),
        "projects": project_rows,
        "tasks": task_rows,
    }


def write_index(root: Path, data: Index) -> Path:
    """Persist `data` to `knowledge/.index.json`. Returns the written path."""
    path = paths.index_file(root)
    storage.write_json(path, data)
    return path


def read_index(root: Path) -> Index:
    """Load the cached index from disk. Raises FileNotFoundError if absent."""
    return storage.read_json(paths.index_file(root))
