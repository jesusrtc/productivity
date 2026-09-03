from __future__ import annotations

from pathlib import Path

import click

from lab import assistant as assistant_db
from lab import paths


def _root() -> Path:
    try:
        return assistant_db.configured_root()
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc


@click.group(name="assistant")
def assistant_group() -> None:
    """Manage the client-owned global Assistant task database."""


@assistant_group.command("path")
def path_cmd() -> None:
    """Print the configured Assistant database path."""
    click.echo(_root())


@assistant_group.command("init")
def init_cmd() -> None:
    """Initialize the configured database without overwriting existing files."""
    target = assistant_db.initialize(_root())
    click.echo(f"initialized Assistant database at {target}")


@assistant_group.group("project")
def project_group() -> None:
    """Manage Assistant project-to-workspace mappings."""


@project_group.command("ls")
def project_ls() -> None:
    rows = list(assistant_db.iter_projects(_root()))
    if not rows:
        click.echo("no Assistant projects")
        return
    for row in rows:
        click.echo(
            f"{row['id']:<24} {row.get('workspace') or '--':<12} "
            f"{row.get('project_path') or '--'}"
        )


@project_group.command("add")
@click.argument("project_id")
@click.option("--name", required=True)
@click.option("--workspace", "workspace_id", required=True)
@click.option("--path", "project_path", type=click.Path(path_type=Path), required=True)
def project_add(project_id: str, name: str, workspace_id: str, project_path: Path) -> None:
    root = _root()
    registry = paths.read_workspace_registry()
    row = next(
        (item for item in registry.get("workspaces") or [] if item.get("id") == workspace_id),
        None,
    )
    if row is None:
        raise click.ClickException(f"registered workspace {workspace_id!r} not found")
    workspace_path = Path(str(row["path"])).expanduser().resolve()
    resolved_project = project_path.expanduser().resolve()
    if workspace_path != resolved_project and workspace_path not in resolved_project.parents:
        raise click.ClickException(
            f"project path {resolved_project} is not inside workspace {workspace_path}"
        )
    try:
        source = assistant_db.create_project(
            root,
            project_id,
            name=name,
            workspace=workspace_id,
            workspace_path=workspace_path,
            project_path=resolved_project,
        )
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"created {project_id} at {source}")


@assistant_group.command("add")
@click.argument("title")
@click.option("--project", "project_id", required=True)
@click.option("--priority", type=click.Choice(assistant_db.PRIORITIES), default="P2")
@click.option("--status", type=click.Choice(assistant_db.STATUSES[:-1]), default="inbox")
@click.option("--due", default=None)
@click.option("--owner", default=None)
@click.option("--tag", "tags", multiple=True)
def add_task(
    title: str,
    project_id: str,
    priority: str,
    status: str,
    due: str | None,
    owner: str | None,
    tags: tuple[str, ...],
) -> None:
    try:
        source = assistant_db.create_task(
            _root(),
            title,
            project_id=project_id,
            priority=priority,
            status=status,
            due=due,
            owner=owner,
            tags=list(tags),
        )
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    metadata, _ = assistant_db.read_markdown(source)
    click.echo(f"{metadata['id']}  {source}")


@assistant_group.command("ls")
@click.option("--status", default="open", help="open or one exact lifecycle status")
@click.option("--priority", type=click.Choice(assistant_db.PRIORITIES), default=None)
@click.option("--project", "project_id", default=None)
def list_tasks(status: str, priority: str | None, project_id: str | None) -> None:
    if status != "open" and status not in assistant_db.STATUSES:
        raise click.ClickException(f"unknown status {status!r}")
    rows = []
    for task in assistant_db.iter_tasks(_root()):
        if status == "open" and task["status"] == "done":
            continue
        if status != "open" and task["status"] != status:
            continue
        if priority and task["priority"] != priority:
            continue
        if project_id and task["project"] != project_id:
            continue
        rows.append(task)
    if not rows:
        click.echo("no Assistant tasks")
        return
    for task in rows:
        click.echo(
            f"{task['id']}  {task['status']:<11} {task['priority']}  "
            f"{task['project']:<18} {task['title']}"
        )


@assistant_group.command("show")
@click.argument("task_id")
def show_task(task_id: str) -> None:
    try:
        source, _metadata, _body = assistant_db.find_task(_root(), task_id)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(source.read_text(encoding="utf-8"))


@assistant_group.command("set")
@click.argument("task_id")
@click.argument("field", type=click.Choice(("title", "status", "priority", "due", "owner")))
@click.argument("value")
def set_task(task_id: str, field: str, value: str) -> None:
    normalized: object = None if value.lower() in {"none", "null", ""} else value
    try:
        source = assistant_db.update_task(_root(), task_id, field, normalized)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"{task_id}.{field} = {normalized!r}  ({source})")


@assistant_group.command("done")
@click.argument("task_id")
def done_task(task_id: str) -> None:
    try:
        source = assistant_db.update_task(_root(), task_id, "status", "done")
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"{task_id}  done  ({source})")


@assistant_group.group("meeting")
def meeting_group() -> None:
    """Manage structured meeting notes in the Assistant database."""


@meeting_group.command("add")
@click.argument("title")
@click.option("--project", "project_id", required=True)
@click.option("--date", default=None, help="Meeting date in YYYY-MM-DD format")
@click.option("--attendee", "attendees", multiple=True)
@click.option("--tag", "tags", multiple=True)
def add_meeting(
    title: str,
    project_id: str,
    date: str | None,
    attendees: tuple[str, ...],
    tags: tuple[str, ...],
) -> None:
    try:
        source = assistant_db.create_meeting(
            _root(),
            title,
            project_id=project_id,
            date=date,
            attendees=list(attendees),
            tags=list(tags),
        )
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    metadata, _ = assistant_db.read_markdown(source)
    click.echo(f"{metadata['id']}  {source}")


@meeting_group.command("ls")
@click.option("--project", "project_id", default=None)
def list_meetings(project_id: str | None) -> None:
    rows = [
        meeting for meeting in assistant_db.iter_meetings(_root())
        if not project_id or meeting["project"] == project_id
    ]
    if not rows:
        click.echo("no Assistant meeting notes")
        return
    rows.sort(key=lambda row: (str(row.get("date") or ""), float(row.get("mtime") or 0)), reverse=True)
    for meeting in rows:
        click.echo(
            f"{meeting['id']}  {meeting.get('date') or '--':<10} "
            f"{meeting['project']:<18} {meeting['title']}"
        )


@meeting_group.command("show")
@click.argument("meeting_id")
def show_meeting(meeting_id: str) -> None:
    try:
        source, _metadata, _body = assistant_db.find_meeting(_root(), meeting_id)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(source.read_text(encoding="utf-8"))
