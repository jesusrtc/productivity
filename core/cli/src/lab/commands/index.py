from __future__ import annotations

import json as _json

import click

from lab import index as index_mod
from lab import paths


@click.group(name="index")
def index_group() -> None:
    """Global index (cache of projects + tasks) commands."""


@index_group.command("rebuild")
def rebuild() -> None:
    """Rebuild the workspace-local index cache from on-disk projects."""
    root = paths.find_monorepo_root()
    data = index_mod.build_index(root)
    path = index_mod.write_index(root, data)
    click.echo(f"wrote {path} ({len(data['projects'])} projects, {len(data['tasks'])} tasks)")


@index_group.command("show")
def show() -> None:
    """Print the cached index as JSON. Rebuilds implicitly if missing."""
    root = paths.find_monorepo_root()
    try:
        data = index_mod.read_index(root)
    except FileNotFoundError:
        data = index_mod.build_index(root)
        index_mod.write_index(root, data)
    click.echo(_json.dumps(data, indent=2))
