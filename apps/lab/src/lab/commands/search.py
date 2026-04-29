from __future__ import annotations

import click

from lab import paths, search as search_mod


@click.command(name="search")
@click.argument("query")
@click.option("--kind", type=click.Choice(["all", "projects", "tasks", "docs"]), default="all")
def search_cmd(query: str, kind: str) -> None:
    """Grep content/ for a keyword across projects, tasks, and markdown docs."""
    root = paths.find_monorepo_root()
    result = search_mod.search(root, query)

    if kind in ("all", "projects") and result["projects"]:
        click.echo(click.style(f"Projects ({len(result['projects'])})", fg="cyan", bold=True))
        for p in result["projects"]:
            click.echo(f"  {p['id']}  [{p['status']}]  {p.get('description', '')[:60]}")

    if kind in ("all", "tasks") and result["tasks"]:
        click.echo(click.style(f"Tasks ({len(result['tasks'])})", fg="cyan", bold=True))
        for t in result["tasks"]:
            click.echo(f"  {t['project_id']}#{t['task_id']}  [{t['status']}]  {t['priority']}  {t['title']}")

    if kind in ("all", "docs") and result["docs"]:
        click.echo(click.style(f"Docs ({len(result['docs'])})", fg="cyan", bold=True))
        for d in result["docs"]:
            click.echo(f"  {d['path']}")
            click.echo(f"    {d['snippet']}")

    total = len(result["projects"]) + len(result["tasks"]) + len(result["docs"])
    if total == 0:
        click.echo("(no matches)")
