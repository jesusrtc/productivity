from __future__ import annotations

import re
from datetime import date, datetime, timezone
from pathlib import Path

import click

from lab import paths, storage
from lab.commands._helpers import require_valid_id as _require_valid_id
from lab.commands._helpers import resolve_project_id as _resolve_project_id
from lab.model import ModelError, Priority, Task
from lab.util import split_csv


_SLUG_RE = re.compile(r"[^a-z0-9]+")
_TASK_SETTABLE = {"title", "priority", "loe", "due", "tags", "labels", "status"}


def _slugify(title: str) -> str:
    return _SLUG_RE.sub("-", title.lower()).strip("-")[:40] or "task"


def _load_tasks(root: Path, project_id: str) -> dict:
    if paths.is_pseudo_project(project_id):
        paths.ensure_self_files(root)
    tjson = paths.tasks_file(root, project_id)
    if not tjson.is_file():
        raise click.ClickException(f"project {project_id!r} has no tasks.json")
    return storage.read_json(tjson)


def _save_tasks(root: Path, project_id: str, data: dict) -> None:
    storage.write_json(paths.tasks_file(root, project_id), data)


def _find_task(tasks_doc: dict, task_id: int) -> dict:
    for t in tasks_doc.get("tasks", []):
        if t["id"] == task_id:
            return t
    raise click.ClickException(f"task #{task_id} not found")


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).astimezone().isoformat(timespec="seconds")


def _iter_all_tasks(root: Path):
    projects_root = root / "content" / "projects"
    if not projects_root.is_dir():
        return
    for child in sorted(projects_root.iterdir()):
        tjson = child / "tasks.json"
        if not tjson.is_file():
            continue
        doc = storage.read_json(tjson)
        for t in doc.get("tasks", []):
            yield child.name, t


def _parse_due_window(value: str) -> int:
    m = re.fullmatch(r"(\d+)d", value)
    if not m:
        raise click.ClickException(f"--due must be Nd (e.g. 7d); got {value!r}")
    return int(m.group(1))


@click.group(name="task")
def task_group() -> None:
    """Task lifecycle commands."""


@task_group.command("new")
@click.argument("title")
@click.option("--project", "project_id", default=None)
@click.option("--priority", type=click.Choice([p.value for p in Priority]), required=True)
@click.option("--loe", type=float, default=None)
@click.option("--due", default=None)
@click.option("--tags", default="")
@click.option("--labels", default="")
@click.option("--file", "create_file", is_flag=True, default=False, help="Create a notes md file")
def new(title: str, project_id: str | None, priority: str, loe: float | None,
        due: str | None, tags: str, labels: str, create_file: bool) -> None:
    """Create a new task in a project (default: PWD project)."""
    root = paths.find_monorepo_root()
    pid = _resolve_project_id(project_id)
    if paths.is_pseudo_project(pid):
        paths.ensure_self_files(root)
    pjson = paths.project_file(root, pid)
    if not pjson.is_file():
        raise click.ClickException(f"project {pid!r} not found")

    tasks_doc = _load_tasks(root, pid)
    task_id = int(tasks_doc.get("next_id", 1))
    slug = _slugify(title)
    notes_file = None
    if create_file:
        notes_rel = f"notes/{task_id:03d}-{slug}.md"
        notes_path = paths.project_dir(root, pid) / notes_rel
        notes_path.parent.mkdir(parents=True, exist_ok=True)
        if not notes_path.exists():
            notes_path.write_text(f"# {title}\n\n", encoding="utf-8")
        notes_file = notes_rel

    try:
        task = Task.from_dict({
            "id": task_id,
            "title": title,
            "status": "todo",
            "priority": priority,
            "loe": loe,
            "due": due,
            "tags": split_csv(tags),
            "labels": split_csv(labels),
            "notes_file": notes_file,
        })
    except ModelError as exc:
        raise click.ClickException(str(exc)) from exc

    tasks_doc["tasks"].append(task.to_dict())
    tasks_doc["next_id"] = task_id + 1
    _save_tasks(root, pid, tasks_doc)

    click.echo(f"{pid}#{task_id}  {title}")


@task_group.command("ls")
@click.option("--project", "project_id", default=None)
@click.option("--status", default=None, help="todo|in_progress|blocked|done|open (= not done)")
@click.option("--priority", default=None, help="Comma-separated (e.g. P0,P1)")
@click.option("--tag", "tag_filter", default=None)
@click.option("--label", "label_filter", default=None)
@click.option("--due", "due_window", default=None, help="Nd — due within N days")
def ls(project_id: str | None, status: str | None, priority: str | None,
       tag_filter: str | None, label_filter: str | None,
       due_window: str | None) -> None:
    """List tasks. Default: all projects. Filter with --project, --status, --priority, --tag, --label, --due."""
    from datetime import timedelta

    root = paths.find_monorepo_root()

    if project_id:
        pid = _require_valid_id(project_id)
        it = ((pid, t) for t in _load_tasks(root, pid).get("tasks", []))
    else:
        it = _iter_all_tasks(root)

    pr_set = set(split_csv(priority)) if priority else None
    horizon = None
    if due_window:
        days = _parse_due_window(due_window)
        horizon = date.today() + timedelta(days=days)

    rows = []
    for pid, t in it:
        if status == "open":
            if t["status"] == "done":
                continue
        elif status:
            if t["status"] != status:
                continue
        if pr_set and t["priority"] not in pr_set:
            continue
        if tag_filter and tag_filter not in (t.get("tags") or []):
            continue
        if label_filter and label_filter not in (t.get("labels") or []):
            continue
        if horizon:
            due = t.get("due")
            if not due or date.fromisoformat(due) > horizon:
                continue
        rows.append((pid, t))

    if not rows:
        click.echo("no tasks")
        return

    w_pid = max(len(pid) for pid, _ in rows)
    for pid, t in rows:
        due = t.get("due") or "--"
        click.echo(
            f"{pid:<{w_pid}}  #{t['id']:<3}  {t['status']:<11}  {t['priority']}  {due:<10}  {t['title']}"
        )


@task_group.command("done")
@click.argument("task_id", type=int)
@click.option("--project", "project_id", default=None)
def done(task_id: int, project_id: str | None) -> None:
    """Mark a task done (sets closed_at)."""
    root = paths.find_monorepo_root()
    pid = _resolve_project_id(project_id)
    doc = _load_tasks(root, pid)
    t = _find_task(doc, task_id)
    t["status"] = "done"
    t["closed_at"] = _now_iso()
    t["updated"] = date.today().isoformat()
    _save_tasks(root, pid, doc)
    click.echo(f"{pid}#{task_id}  done")


@task_group.command("reopen")
@click.argument("task_id", type=int)
@click.option("--project", "project_id", default=None)
def reopen(task_id: int, project_id: str | None) -> None:
    """Reopen a done task (status → in_progress, clears closed_at)."""
    root = paths.find_monorepo_root()
    pid = _resolve_project_id(project_id)
    doc = _load_tasks(root, pid)
    t = _find_task(doc, task_id)
    t["status"] = "in_progress"
    t["closed_at"] = None
    t["updated"] = date.today().isoformat()
    _save_tasks(root, pid, doc)
    click.echo(f"{pid}#{task_id}  reopened")


@task_group.command("block")
@click.argument("task_id", type=int)
@click.argument("reason")
@click.option("--project", "project_id", default=None)
def block(task_id: int, reason: str, project_id: str | None) -> None:
    """Mark a task blocked with a reason."""
    root = paths.find_monorepo_root()
    pid = _resolve_project_id(project_id)
    doc = _load_tasks(root, pid)
    t = _find_task(doc, task_id)
    t["status"] = "blocked"
    t["blocker"] = reason
    t["updated"] = date.today().isoformat()
    _save_tasks(root, pid, doc)
    click.echo(f"{pid}#{task_id}  blocked: {reason}")


@task_group.command("unblock")
@click.argument("task_id", type=int)
@click.option("--project", "project_id", default=None)
def unblock(task_id: int, project_id: str | None) -> None:
    """Clear a task's blocker (status → in_progress)."""
    root = paths.find_monorepo_root()
    pid = _resolve_project_id(project_id)
    doc = _load_tasks(root, pid)
    t = _find_task(doc, task_id)
    t["status"] = "in_progress"
    t["blocker"] = None
    t["updated"] = date.today().isoformat()
    _save_tasks(root, pid, doc)
    click.echo(f"{pid}#{task_id}  unblocked")


@task_group.command("show")
@click.argument("task_id", type=int)
@click.option("--project", "project_id", default=None)
def show(task_id: int, project_id: str | None) -> None:
    """Print a task's fields and notes file content (if any)."""
    import json as _json

    root = paths.find_monorepo_root()
    pid = _resolve_project_id(project_id)
    doc = _load_tasks(root, pid)
    t = _find_task(doc, task_id)
    click.echo(_json.dumps(t, indent=2))
    notes_file = t.get("notes_file")
    if notes_file:
        notes_path = paths.project_dir(root, pid) / notes_file
        if notes_path.is_file():
            click.echo("")
            click.echo(f"--- {notes_file} ---")
            click.echo(notes_path.read_text())


@task_group.command("set")
@click.argument("task_id", type=int)
@click.argument("field")
@click.argument("value")
@click.option("--project", "project_id", default=None)
def set_field(task_id: int, field: str, value: str, project_id: str | None) -> None:
    """Update a single task field (validated)."""
    if field not in _TASK_SETTABLE:
        raise click.ClickException(
            f"{field} is not settable. Allowed: {sorted(_TASK_SETTABLE)}"
        )
    root = paths.find_monorepo_root()
    pid = _resolve_project_id(project_id)
    doc = _load_tasks(root, pid)
    t = _find_task(doc, task_id)

    if field in {"tags", "labels"}:
        t[field] = split_csv(value)
    elif field == "loe":
        if value in {"", "null", "none"}:
            t[field] = None
        else:
            try:
                t[field] = float(value)
            except ValueError as exc:
                raise click.ClickException(f"loe: {value!r} is not a number") from exc
    elif field in {"priority", "due", "status", "title"}:
        t[field] = value
    else:
        t[field] = value

    t["updated"] = date.today().isoformat()

    try:
        Task.from_dict(t)
    except ModelError as exc:
        raise click.ClickException(str(exc)) from exc

    _save_tasks(root, pid, doc)
    click.echo(f"{pid}#{task_id}.{field} = {t[field]!r}")
