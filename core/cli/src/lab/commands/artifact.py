from __future__ import annotations

from datetime import date

import click

from lab import paths, storage
from lab.commands._helpers import resolve_project_id as _resolve_project_id


VALID_TYPES = [
    "google_doc",
    "spreadsheet",
    "retina_chart",
    "jira",
    "confluence",
    "slack",
    "github",
    "url",
]


@click.group(name="artifact")
def artifact_group() -> None:
    """Track external artifacts (google docs, jira, charts, etc.) for a project."""


@artifact_group.command("add")
@click.argument("url")
@click.option("--project", "project_id", default=None)
@click.option("--type", "atype", type=click.Choice(VALID_TYPES), default="url")
@click.option("--title", default="")
@click.option("--desc", default="")
@click.option(
    "--file",
    "file_path",
    default=None,
    help="Path (relative to the project) of the local doc this artifact mirrors online. "
    "The web UI surfaces a 'Published at' banner on that doc; an empty --file makes the "
    "artifact project-scoped (shown on the project dashboard only).",
)
def add(url: str, project_id: str | None, atype: str, title: str, desc: str,
        file_path: str | None) -> None:
    """Append an artifact entry to project.json.artifacts[]."""
    root = paths.find_monorepo_root()
    pid = _resolve_project_id(project_id)
    pjson = paths.project_file(root, pid)
    if not pjson.is_file():
        raise click.ClickException(f"project {pid!r} not found")
    data = storage.read_json(pjson)
    data.setdefault("artifacts", [])
    next_id = 1 + max((a.get("id", 0) for a in data["artifacts"]), default=0)
    entry: dict = {
        "id": next_id,
        "type": atype,
        "url": url,
        "title": title,
        "description": desc,
        "added": date.today().isoformat(),
    }
    if file_path:
        entry["file"] = file_path.lstrip("./")
    data["artifacts"].append(entry)
    data["updated"] = date.today().isoformat()
    storage.write_json(pjson, data)
    if file_path:
        click.echo(f"{pid}: added artifact #{next_id} {url} (linked to {entry['file']})")
    else:
        click.echo(f"{pid}: added artifact #{next_id} {url}")


@artifact_group.command("ls")
@click.option("--project", "project_id", default=None)
def ls(project_id: str | None) -> None:
    """List artifacts for a project."""
    root = paths.find_monorepo_root()
    pid = _resolve_project_id(project_id)
    pjson = paths.project_file(root, pid)
    if not pjson.is_file():
        raise click.ClickException(f"project {pid!r} not found")
    arts = storage.read_json(pjson).get("artifacts", [])
    if not arts:
        click.echo("(no artifacts)")
        return
    for a in arts:
        click.echo(
            f"  [{a.get('id','?')}] {a.get('type','?'):<12} {a.get('title','(no title)')}"
        )
        click.echo(f"       {a.get('url','')}")
        if a.get("file"):
            click.echo(f"       ↳ mirrors {a['file']}")
        if a.get("description"):
            click.echo(f"       {a['description']}")


@artifact_group.command("rm")
@click.argument("idx", type=int)
@click.option("--project", "project_id", default=None)
def rm(idx: int, project_id: str | None) -> None:
    """Remove artifact by id (preferred) or list index."""
    root = paths.find_monorepo_root()
    pid = _resolve_project_id(project_id)
    pjson = paths.project_file(root, pid)
    if not pjson.is_file():
        raise click.ClickException(f"project {pid!r} not found")
    data = storage.read_json(pjson)
    arts = data.get("artifacts", [])
    # Try by id first
    by_id = next(((i, a) for i, a in enumerate(arts) if a.get("id") == idx), None)
    if by_id is not None:
        pos, _ = by_id
        removed = arts.pop(pos)
    elif 0 <= idx < len(arts):
        removed = arts.pop(idx)
    else:
        raise click.ClickException(f"no artifact matching id/index {idx}")
    data["updated"] = date.today().isoformat()
    storage.write_json(pjson, data)
    click.echo(f"{pid}: removed artifact {removed.get('url','')}")
