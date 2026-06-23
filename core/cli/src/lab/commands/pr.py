from __future__ import annotations

from datetime import date

import click

from lab import paths, storage
from lab.commands._helpers import resolve_project_id as _resolve_project_id


@click.group(name="pr")
def pr_group() -> None:
    """Track PRs associated with a project."""


@pr_group.command("add")
@click.argument("url")
@click.option("--project", "project_id", default=None)
@click.option("--mp", default="")
@click.option("--title", default="")
@click.option("--status", type=click.Choice(["open", "merged", "closed", "draft"]), default="open")
def add(url: str, project_id: str | None, mp: str, title: str, status: str) -> None:
    """Append a PR entry to project.json.prs[]."""
    root = paths.find_monorepo_root()
    pid = _resolve_project_id(project_id)
    pjson = paths.project_file(root, pid)
    if not pjson.is_file():
        raise click.ClickException(f"project {pid!r} not found")
    data = storage.read_json(pjson)
    data.setdefault("prs", [])
    entry = {
        "url": url,
        "mp": mp,
        "title": title,
        "status": status,
        "added": date.today().isoformat(),
    }
    data["prs"].append(entry)
    data["updated"] = date.today().isoformat()
    storage.write_json(pjson, data)
    click.echo(f"{pid}: added PR {url}")


@pr_group.command("ls")
@click.option("--project", "project_id", default=None)
def ls(project_id: str | None) -> None:
    """List PRs for a project."""
    root = paths.find_monorepo_root()
    pid = _resolve_project_id(project_id)
    pjson = paths.project_file(root, pid)
    if not pjson.is_file():
        raise click.ClickException(f"project {pid!r} not found")
    prs = storage.read_json(pjson).get("prs", [])
    if not prs:
        click.echo("(no PRs)")
        return
    for i, p in enumerate(prs):
        click.echo(
            f"  [{i}] {p.get('status','?'):<7} {p.get('mp','?'):<15} "
            f"{p.get('url','')} {p.get('title','')}"
        )


@pr_group.command("rm")
@click.argument("idx", type=int)
@click.option("--project", "project_id", default=None)
def rm(idx: int, project_id: str | None) -> None:
    """Remove PR at index."""
    root = paths.find_monorepo_root()
    pid = _resolve_project_id(project_id)
    pjson = paths.project_file(root, pid)
    if not pjson.is_file():
        raise click.ClickException(f"project {pid!r} not found")
    data = storage.read_json(pjson)
    prs = data.get("prs", [])
    if idx < 0 or idx >= len(prs):
        raise click.ClickException(f"idx {idx} out of range (0..{len(prs)-1})")
    removed = prs.pop(idx)
    data["updated"] = date.today().isoformat()
    storage.write_json(pjson, data)
    click.echo(f"{pid}: removed PR {removed.get('url','')}")
