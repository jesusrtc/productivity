from __future__ import annotations

from pathlib import Path
import json

from lab import assistant_records as records, assistant_migration, assistant_documents as documents

import click

from lab import assistant as assistant_db
from lab import paths


EDITABLE_FIELDS = (
    "project", "workspace", "parent", "position",
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
@click.option("--workspace", "workspace_id", default=None)
@click.option("--project", "project_id", default=None)
@click.option("--priority", type=click.Choice(assistant_db.PRIORITIES), default="P2")
@click.option("--status", type=click.Choice((*assistant_db.STATUSES[:-1], "not_started")), default="inbox")
@click.option("--due", default=None)
@click.option("--owner", default=None)
@click.option("--tag", "tags", multiple=True)
def add_task(
    title: str,
    project_id: str | None,
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
            project_id=project_id,
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
@click.option("--project", "project_id", default=None)
def list_tasks(status: str, priority: str | None, workspace_id: str | None, project_id: str | None) -> None:
    if status != "open" and status not in (*assistant_db.STATUSES,'not_started','skipped','cancelled'):
        raise click.ClickException(f"unknown status {status!r}")
    rows = []
    for task in assistant_db.iter_tasks(_root()):
        if status == "open" and task["status"] in {"done","skipped","cancelled"}:
            continue
        if status != "open" and task["status"] != status:
            continue
        if priority and task["priority"] != priority:
            continue
        if workspace_id and task["workspace"] != workspace_id:
            continue
        if project_id and task.get("project") != project_id:
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
    click.echo(records.encode_document(*assistant_db.read_markdown(source)).decode())


@assistant_group.command("set")
@click.argument("task_id")
@click.argument("field", type=click.Choice(EDITABLE_FIELDS))
@click.argument("value")
def set_task(task_id: str, field: str, value: str) -> None:
    if field == 'parent' and value not in {'null','none',''}:
        try:
            value = json.loads(value)
        except ValueError as exc:
            raise click.ClickException('Parent must be JSON: {"type":"task","id":"…"}') from exc
    normalized: object = None if isinstance(value, str) and value.lower() in {"none", "null", ""} else value
    if field == 'position' and isinstance(normalized, str):
        normalized = assistant_db._decode_scalar(normalized)
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
@click.option("--status", type=click.Choice((*assistant_db.STATUSES[:-1], "not_started")), default="inbox")
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
    if status != "open" and status not in (*assistant_db.STATUSES,'not_started','skipped','cancelled'):
        raise click.ClickException(f"unknown status {status!r}")
    rows = []
    for subtask in assistant_db.iter_subtasks(_root()):
        if status == "open" and subtask["status"] in {"done","skipped","cancelled"}:
            continue
        if status != "open" and subtask["status"] != status:
            continue
        if priority and subtask["priority"] != priority:
            continue
        if workspace_id and subtask["workspace"] != workspace_id:
            continue
        if parent_id and (subtask["parent"].get("id") if isinstance(subtask["parent"], dict) else subtask["parent"]) != parent_id:
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
    click.echo(records.encode_document(*assistant_db.read_markdown(source)).decode())


@subtask_group.command("set")
@click.argument("subtask_id")
@click.argument("field", type=click.Choice(EDITABLE_FIELDS))
@click.argument("value")
def set_subtask(subtask_id: str, field: str, value: str) -> None:
    if field == 'parent' and value not in {'null','none',''}:
        try:
            value = json.loads(value)
        except ValueError as exc:
            raise click.ClickException('Parent must be JSON: {"type":"task","id":"…"}') from exc
    normalized: object = None if isinstance(value, str) and value.lower() in {"none", "null", ""} else value
    if field == 'position' and isinstance(normalized, str):
        normalized = assistant_db._decode_scalar(normalized)
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
    click.echo(records.encode_document(*assistant_db.read_markdown(source)).decode())


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
    click.echo(records.encode_document(*assistant_db.read_markdown(source)).decode())


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


@assistant_group.command("migrate")
@click.option("--apply", "apply_changes", is_flag=True, help="Apply after staging and verifying a full backup")
@click.option("--dry-run", is_flag=True, help="Inspect only (the default)")
@click.option("--embedded", is_flag=True, help="Keep subtabs inside their task/note Markdown file")
def migrate_cmd(apply_changes, dry_run, embedded):
    """Move existing documents into independent tasks/, notes/, and projects/."""
    if apply_changes and dry_run:
        raise click.ClickException("Choose --apply or --dry-run")
    try:
        result = (documents.migrate if embedded else assistant_migration.migrate)(_root(), dry_run=not apply_changes)
    except (OSError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(json.dumps(result, ensure_ascii=False, indent=2))


@assistant_group.command("verify")
def verify_cmd():
    """Check document IDs, aliases, parents, project and workspace references."""
    try:
        if not records.enabled(_root()):
            raise ValueError("Run lab assistant migrate first")
        click.echo(json.dumps(records.verify(_root()), indent=2))
    except (OSError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc


def _v2_root():
    root = _root()
    if not records.enabled(root):
        raise click.ClickException("Run lab assistant migrate --apply first")
    return root


@assistant_group.group("project")
def project_group():
    """Independent projects; each can span several workspaces."""


@project_group.command("add")
@click.argument("project_id")
@click.option("--name", required=True)
def project_add(project_id, name):
    try:
        click.echo(records.create(_v2_root(), 'project', name, identifier=project_id,
                                  status='active'))
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc


@project_group.command("ls")
def project_ls():
    for row in records.records(_v2_root(), 'projects'):
        click.echo(f"{row['id']}  {row['title']}")


@assistant_group.group("note")
def note_group():
    """Plain notes and subtabs, with optional project/workspace/parent links."""


@note_group.command("add")
@click.argument("title")
@click.option("--workspace", default=None)
@click.option("--project", default=None)
@click.option("--parent", default=None, help="A task or note ID")
@click.option("--parent-type", type=click.Choice(['task','note']), default='note')
@click.option("--kind", type=click.Choice(['plain','subtab','thread']), default='plain')
def note_add(title, workspace, project, parent, parent_type, kind):
    try:
        click.echo(records.create(_v2_root(), 'note', title, workspace=workspace, project=project,
                                  note_type='subtab' if parent or kind == 'thread' else kind, parent={'type':parent_type,'id':parent} if parent else None))
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc


@note_group.command("ls")
@click.option("--workspace", default=None)
@click.option("--project", default=None)
def note_ls(workspace, project):
    for row in records.records(_v2_root(), 'notes'):
        if row.get('embedded') or workspace and row.get('workspace') != workspace or project and row.get('project') != project:
            continue
        click.echo(f"{row['id']}  {row.get('note_type')}  {row['title']}")


@note_group.command("show")
@click.argument("note_id")
def note_show(note_id):
    try:
        click.echo(records.encode_document(*records.resolve(_v2_root(), note_id, 'notes')[1:]).decode())
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc


@note_group.command("set")
@click.argument("note_id")
@click.argument("field", type=click.Choice(['title','tldr','workspace','project','parent','position','date','series','status','priority','due','owner']))
@click.argument("value")
def note_set(note_id, field, value):
    try:
        click.echo(records.update(_v2_root(), note_id, field, assistant_db._decode_scalar(value), collection='notes'))
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc


@assistant_group.group("subtab")
def subtab_group():
    """Nested document tabs; the unified name for child notes and discussions."""


@subtab_group.command("add")
@click.argument("title")
@click.option("--parent", required=True, help="Parent task or note ID")
@click.option("--parent-type", required=True, type=click.Choice(['task', 'note']))
@click.option("--top-level", is_flag=True, help="Place beside the main tab; parent must be the document root")
def subtab_add(title, parent, parent_type, top_level):
    try:
        click.echo(records.create_subtab(_v2_root(), title, parent={'type':parent_type,'id':parent}, top_level=top_level))
    except (OSError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc


@subtab_group.command("ls")
@click.option("--parent", required=True)
@click.option("--parent-type", required=True, type=click.Choice(['task', 'note']))
def subtab_ls(parent, parent_type):
    try:
        root = _v2_root()
        records.resolve(root, parent, parent_type + 's')
        for row in records.records(root):
            if records.parent_key(row) == (parent_type, parent):
                click.echo(f"{row['id']}  {row['title']}  {row['path']}")
    except (OSError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc


@subtab_group.command('show')
@click.argument('identifier')
def subtab_show(identifier):
    try:
        click.echo(records.encode_document(*records.resolve(_v2_root(), identifier)[1:]).decode())
    except (OSError,ValueError) as exc:
        raise click.ClickException(str(exc)) from exc


@subtab_group.command('set')
@click.argument('identifier')
@click.argument('field',type=click.Choice(EDITABLE_FIELDS))
@click.argument('value')
def subtab_set(identifier, field, value):
    try:
        click.echo(records.update(_v2_root(),identifier,field,assistant_db._decode_scalar(value)))
    except (OSError,ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
