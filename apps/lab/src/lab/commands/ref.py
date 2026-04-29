"""``lab ref`` — manage a project's external reference URLs.

References are inbound source material (articles, Slack threads, blog
posts, external specs) that inform the project. They live under
``project.json.references[]`` and surface in the UI as a virtual
``external-references/`` folder in the sidebar.

Distinct from ``artifacts``: artifacts are canonical online mirrors of
local work (Google Doc one-pager, Confluence page) — references point
inbound (context we consume, not content we author).

    lab ref add https://go/foo-design --name "Foo design doc"
    lab ref add https://example.com/article
    lab ref ls
    lab ref rm 2
"""
from __future__ import annotations

from datetime import date

import click

from lab import paths, storage
from lab.commands._helpers import resolve_project_id as _resolve_project_id


@click.group(name="ref")
def ref_group() -> None:
    """Track external URLs a project references (reading material, threads, …)."""


@ref_group.command("add")
@click.argument("url")
@click.option("--project", "project_id", default=None,
              help="Project id (defaults to the project of the current dir).")
@click.option("--name", "title", default="",
              help="Display name; falls back to the URL itself.")
@click.option("--note", default="",
              help="One-line context about why this reference matters.")
def add(url: str, project_id: str | None, title: str, note: str) -> None:
    """Append a reference entry to ``project.json.references[]``."""
    root = paths.find_monorepo_root()
    pid = _resolve_project_id(project_id)
    pjson = paths.project_file(root, pid)
    if not pjson.is_file():
        raise click.ClickException(f"project {pid!r} not found")
    data = storage.read_json(pjson)
    data.setdefault("references", [])
    next_id = 1 + max((r.get("id", 0) for r in data["references"]), default=0)
    entry = {
        "id": next_id,
        "url": url,
        "title": title or url,
        "note": note,
        "added": date.today().isoformat(),
    }
    data["references"].append(entry)
    data["updated"] = date.today().isoformat()
    storage.write_json(pjson, data)
    click.echo(f"{pid}: added reference #{next_id} {entry['title']}")


@ref_group.command("ls")
@click.option("--project", "project_id", default=None,
              help="Project id (defaults to the project of the current dir).")
def ls(project_id: str | None) -> None:
    """List references for a project."""
    root = paths.find_monorepo_root()
    pid = _resolve_project_id(project_id)
    pjson = paths.project_file(root, pid)
    if not pjson.is_file():
        raise click.ClickException(f"project {pid!r} not found")
    refs = storage.read_json(pjson).get("references", [])
    if not refs:
        click.echo("(no references)")
        return
    for r in refs:
        click.echo(f"  [{r.get('id','?')}] {r.get('title','(no title)')}")
        click.echo(f"       {r.get('url','')}")
        if r.get("note"):
            click.echo(f"       {r['note']}")


@ref_group.command("rm")
@click.argument("idx", type=int)
@click.option("--project", "project_id", default=None,
              help="Project id (defaults to the project of the current dir).")
def rm(idx: int, project_id: str | None) -> None:
    """Remove a reference by id (preferred) or list index."""
    root = paths.find_monorepo_root()
    pid = _resolve_project_id(project_id)
    pjson = paths.project_file(root, pid)
    if not pjson.is_file():
        raise click.ClickException(f"project {pid!r} not found")
    data = storage.read_json(pjson)
    refs = data.get("references", [])
    by_id = next(((i, r) for i, r in enumerate(refs) if r.get("id") == idx), None)
    if by_id is not None:
        pos, _ = by_id
        removed = refs.pop(pos)
    elif 0 <= idx < len(refs):
        removed = refs.pop(idx)
    else:
        raise click.ClickException(f"no reference matching id/index {idx}")
    data["updated"] = date.today().isoformat()
    storage.write_json(pjson, data)
    click.echo(f"{pid}: removed reference {removed.get('title', removed.get('url', ''))}")
