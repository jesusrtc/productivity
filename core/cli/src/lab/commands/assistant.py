from __future__ import annotations

from pathlib import Path

import click

from lab import assistant as assistant_db
from lab import paths


EDITABLE_FIELDS = (
    "title",
    "group",
    "tldr",
    "status",
    "priority",
    "due",
    "scheduled",
    "defer_until",
    "recurrence",
    "recurrence_anchor",
    "source",
    "owner",
    "waiting_on",
    "waiting_since",
    "follow_up_at",
    "last_follow_up_at",
    "follow_up_channel",
    "reviewer",
    "review_requested_at",
    "executor",
)


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


@assistant_group.group("workspace")
def workspace_group() -> None:
    """Manage Assistant workspace-to-vault mappings."""


@workspace_group.command("ls")
def workspace_ls() -> None:
    rows = list(assistant_db.iter_workspaces(_root()))
    if not rows:
        click.echo("no Assistant workspaces")
        return
    for row in rows:
        click.echo(
            f"{row['id']:<24} {row.get('vault') or '--':<12} "
            f"{row.get('workspace_path') or '--'}"
        )


@workspace_group.command("add")
@click.argument("workspace_id")
@click.option("--name", required=True)
@click.option("--vault", "vault_id", required=True)
@click.option("--path", "workspace_path", type=click.Path(path_type=Path), required=True)
def workspace_add(workspace_id: str, name: str, vault_id: str, workspace_path: Path) -> None:
    root = _root()
    registry = paths.read_vault_registry()
    row = next(
        (item for item in registry.get("vaults") or [] if item.get("id") == vault_id),
        None,
    )
    if row is None:
        raise click.ClickException(f"registered vault {vault_id!r} not found")
    vault_path = Path(str(row["path"])).expanduser().resolve()
    resolved_workspace = workspace_path.expanduser().resolve()
    if vault_path != resolved_workspace and vault_path not in resolved_workspace.parents:
        raise click.ClickException(
            f"workspace path {resolved_workspace} is not inside vault {vault_path}"
        )
    try:
        source = assistant_db.create_workspace(
            root,
            workspace_id,
            name=name,
            vault=vault_id,
            vault_path=vault_path,
            workspace_path=resolved_workspace,
        )
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"created {workspace_id} at {source}")


@assistant_group.command("add")
@click.argument("title")
@click.option("--workspace", "workspace_id", required=True)
@click.option("--priority", type=click.Choice(assistant_db.PRIORITIES), default="P2")
@click.option("--status", type=click.Choice(assistant_db.STATUSES[:-1]), default="inbox")
@click.option("--due", default=None)
@click.option("--owner", default=None)
@click.option("--tag", "tags", multiple=True)
def add_task(
    title: str,
    workspace_id: str,
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
            workspace_id=workspace_id,
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
@click.option("--workspace", "workspace_id", default=None)
def list_tasks(status: str, priority: str | None, workspace_id: str | None) -> None:
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
        if workspace_id and task["workspace"] != workspace_id:
            continue
        rows.append(task)
    if not rows:
        click.echo("no Assistant tasks")
        return
    for task in rows:
        click.echo(
            f"{task['id']}  {task['status']:<11} {task['priority']}  "
            f"{task['workspace']:<18} {task['title']}"
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
@click.argument("field", type=click.Choice(EDITABLE_FIELDS))
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


@assistant_group.group("subtask")
def subtask_group() -> None:
    """Manage first-class Markdown subtasks in the Assistant database."""


@subtask_group.command("add")
@click.argument("title")
@click.option("--parent", "parent_id", required=True)
@click.option("--workspace", "workspace_id", default=None, help="Owning workspace; defaults to the parent task workspace.")
@click.option("--priority", type=click.Choice(assistant_db.PRIORITIES), default="P2")
@click.option("--status", type=click.Choice(assistant_db.STATUSES[:-1]), default="inbox")
@click.option("--due", default=None)
@click.option("--owner", default=None)
@click.option("--tag", "tags", multiple=True)
def add_subtask(
    title: str,
    parent_id: str,
    workspace_id: str | None,
    priority: str,
    status: str,
    due: str | None,
    owner: str | None,
    tags: tuple[str, ...],
) -> None:
    try:
        source = assistant_db.create_subtask(
            _root(),
            title,
            parent=parent_id,
            workspace=workspace_id,
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


@subtask_group.command("ls")
@click.option("--parent", "parent_id", default=None)
@click.option("--status", default="open", help="open or one exact lifecycle status")
@click.option("--priority", type=click.Choice(assistant_db.PRIORITIES), default=None)
@click.option("--workspace", "workspace_id", default=None)
def list_subtasks(
    parent_id: str | None,
    status: str,
    priority: str | None,
    workspace_id: str | None,
) -> None:
    if status != "open" and status not in assistant_db.STATUSES:
        raise click.ClickException(f"unknown status {status!r}")
    rows = []
    for subtask in assistant_db.iter_subtasks(_root()):
        if status == "open" and subtask["status"] == "done":
            continue
        if status != "open" and subtask["status"] != status:
            continue
        if priority and subtask["priority"] != priority:
            continue
        if workspace_id and subtask["workspace"] != workspace_id:
            continue
        if parent_id and subtask["parent"] != parent_id:
            continue
        rows.append(subtask)
    if not rows:
        click.echo("no Assistant subtasks")
        return
    for subtask in rows:
        click.echo(
            f"{subtask['id']}  {subtask['status']:<15} {subtask['priority']}  "
            f"{subtask['workspace']:<18} {subtask['parent']}  {subtask['title']}"
        )


@subtask_group.command("show")
@click.argument("subtask_id")
def show_subtask(subtask_id: str) -> None:
    try:
        source, _metadata, _body = assistant_db.find_subtask(_root(), subtask_id)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(source.read_text(encoding="utf-8"))


@subtask_group.command("set")
@click.argument("subtask_id")
@click.argument("field", type=click.Choice(EDITABLE_FIELDS))
@click.argument("value")
def set_subtask(subtask_id: str, field: str, value: str) -> None:
    normalized: object = None if value.lower() in {"none", "null", ""} else value
    try:
        source = assistant_db.update_subtask(_root(), subtask_id, field, normalized)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"{subtask_id}.{field} = {normalized!r}  ({source})")


@subtask_group.command("done")
@click.argument("subtask_id")
def done_subtask(subtask_id: str) -> None:
    try:
        source = assistant_db.update_subtask(_root(), subtask_id, "status", "done")
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"{subtask_id}  done  ({source})")


@assistant_group.group("meeting")
def meeting_group() -> None:
    """Manage structured meeting notes in the Assistant database."""


@meeting_group.command("add")
@click.argument("title")
@click.option("--workspace", "workspace_id", required=True)
@click.option("--date", default=None, help="Meeting date in YYYY-MM-DD format")
@click.option("--undated", is_flag=True)
@click.option("--series", default=None)
@click.option("--raw-file", type=click.Path(path_type=Path), default=None)
@click.option("--attendee", "attendees", multiple=True)
@click.option("--tag", "tags", multiple=True)
def add_meeting(
    title: str,
    workspace_id: str,
    date: str | None,
    undated: bool,
    series: str | None,
    raw_file: Path | None,
    attendees: tuple[str, ...],
    tags: tuple[str, ...],
) -> None:
    try:
        source = assistant_db.create_meeting(
            _root(),
            title,
            workspace_id=workspace_id,
            date=date,
            undated=undated,
            series=series,
            raw_file=raw_file,
            attendees=list(attendees),
            tags=list(tags),
        )
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    metadata, _ = assistant_db.read_markdown(source)
    click.echo(f"{metadata['id']}  {source}")


@meeting_group.command("ls")
@click.option("--workspace", "workspace_id", default=None)
@click.option("--series", "series_id", default=None)
def list_meetings(workspace_id: str | None, series_id: str | None) -> None:
    root = _root()
    if series_id is not None:
        try:
            source, _, _ = assistant_db.find_meeting_series(root, series_id, workspace_id)
            workspace_id = source.parent.parent.name
        except ValueError as exc:
            raise click.ClickException(str(exc)) from exc
    rows = [
        meeting for meeting in assistant_db.meeting_list_rows(root)
        if (not workspace_id or meeting["workspace"] == workspace_id)
        and (series_id is None or meeting.get("series") == series_id)
    ]
    if not rows:
        click.echo("no Assistant meeting notes")
        return
    for meeting in rows:
        click.echo(
            f"{meeting['id']}  {meeting.get('date') or '--':<10} "
            f"{meeting['workspace']:<18} {meeting['title']}"
        )


@meeting_group.command("show")
@click.argument("meeting_id")
def show_meeting(meeting_id: str) -> None:
    try:
        source, _metadata, _body = assistant_db.find_meeting(_root(), meeting_id)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(source.read_text(encoding="utf-8"))


@meeting_group.command("set")
@click.argument("meeting_id")
@click.argument("field", type=click.Choice(("title", "date", "series", "tldr")))
@click.argument("value")
def set_meeting(meeting_id, field, value):
    try:
        source = assistant_db.update_meeting(_root(), meeting_id, field, None if value in {"none", "null"} else value)
    except (OSError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(str(source))


@meeting_group.group("series")
def series_group():
    """Explicit recurring series, scoped to a workspace."""


@series_group.command("add")
@click.argument("series_id")
@click.option("--workspace", required=True)
@click.option("--title", required=True)
def series_add(series_id, workspace, title):
    try:
        source = assistant_db.create_meeting_series(_root(), series_id, workspace_id=workspace, title=title)
    except (OSError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(str(source))


@series_group.command("ls")
@click.option("--workspace", default=None)
def series_ls(workspace):
    for row in assistant_db.iter_meeting_series(_root()):
        if workspace is None or row["workspace"] == workspace:
            click.echo(f"{row['id']}  {row['workspace']}  {row['title']}")


@series_group.command("show")
@click.argument("series_id")
@click.option("--workspace", default=None)
def series_show(series_id, workspace):
    try:
        source, _, _ = assistant_db.find_meeting_series(_root(), series_id, workspace)
    except (OSError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(source.read_text(encoding="utf-8"))


@meeting_group.group("raw")
def raw_group():
    """Capture an unchanged original once; read it as plain text."""


@raw_group.command("add")
@click.argument("meeting_id")
@click.option("--file", required=True, type=click.Path(path_type=Path))
def raw_add(meeting_id, file):
    try:
        source = assistant_db.add_meeting_raw(_root(), meeting_id, file)
    except (OSError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(str(source))


@raw_group.command("show")
@click.argument("meeting_id")
def raw_show(meeting_id):
    try:
        root = _root()
        meeting, _, _ = assistant_db.find_meeting(root, meeting_id)
        data = assistant_db.meeting_raw_path(root, meeting).read_bytes()
        data.decode("utf-8")
    except (OSError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.get_binary_stream("stdout").write(data)


@meeting_group.group("content")
def content_group():
    """Separate meeting questions and documents."""


@content_group.command("add")
@click.argument("title")
@click.option("--meeting", required=True)
@click.option("--kind", required=True, type=click.Choice(("question", "document")))
@click.option("--file", default=None, type=click.Path(path_type=Path))
@click.option("--url", default=None)
def content_add(title, meeting, kind, file, url):
    try:
        source = assistant_db.create_meeting_content(_root(), title, meeting_id=meeting, kind=kind, file=file, url=url)
    except (OSError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"{source.stem}  {source}")


@content_group.command("ls")
@click.option("--meeting", required=True)
def content_ls(meeting):
    try:
        root = _root()
        source, _, _ = assistant_db.find_meeting(root, meeting)
        for row in assistant_db.iter_meeting_contents(root, source):
            click.echo(f"{row['id']}  {row['kind']}  {row['title']}")
    except (OSError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc


@content_group.command("show")
@click.argument("content_id")
@click.option("--meeting", required=True)
def content_show(content_id, meeting):
    try:
        root = _root()
        source, _, _ = assistant_db.find_meeting(root, meeting)
        rows = [row for row in assistant_db.iter_meeting_contents(root, source) if row["id"] == content_id]
        if len(rows) != 1:
            raise ValueError("meeting content not found or not unique")
        click.echo((root / rows[0]["path"]).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc


@assistant_group.command("repeat")
@click.argument("task_id")
def repeat_task(task_id):
    """Create the next occurrence of a completed recurring task, once."""
    from lab.assistant_recurrence import advance
    try:
        source = advance(_root(), task_id)
    except (OSError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"{source.stem}  {source}")
