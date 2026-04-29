"""``lab link`` — manage the ``links/`` folder of symlinks into other docs.

A project's ``links/`` folder is a curated set of symlinks pointing at docs
that live elsewhere in the monorepo — other projects' one-pagers, shared
wikis under ``knowledge/wikis/``, meeting notes. The server already lists
these in the file sidebar, so they read exactly like local docs without
duplicating content.

Example:

    cd knowledge/projects/foo
    lab link add ../bar/docs/one-pager.md            # -> links/one-pager.md
    lab link add knowledge/wikis/platform.md         # -> links/platform.md
    lab link add ../bar/docs/vision.md --name vision # -> links/vision.md
"""
from __future__ import annotations

import os
from pathlib import Path

import click

from lab import paths
from lab.commands._helpers import resolve_project_id as _resolve_project_id


def _links_dir(root: Path, pid: str) -> Path:
    return paths.project_dir(root, pid) / "links"


def _resolve_target(root: Path, pdir: Path, target: str) -> Path:
    """Accept absolute path, monorepo-relative path, or path relative to PWD.

    Returns an absolute path that will become the symlink target. We
    deliberately do NOT follow the chain of symlinks on the target —
    ``os.path.abspath`` normalizes ``..`` but preserves symlinks, so
    linking ``docs/vision.md`` points to that path (stable) rather than
    jumping to whatever file the symlink currently resolves to.
    """
    if target.startswith("/"):
        return Path(os.path.abspath(target))
    mono = Path(os.path.abspath(root / target))
    if mono.exists() or mono.is_symlink():
        return mono
    return Path(os.path.abspath(target))


@click.group(name="link")
def link_group() -> None:
    """Manage the per-project ``links/`` folder of internal symlinks."""


@link_group.command("add")
@click.argument("target")
@click.option("--project", "project_id", default=None,
              help="Project id (defaults to the project of the current dir).")
@click.option("--name", default=None,
              help="Symlink filename under links/ (defaults to target basename).")
def add(target: str, project_id: str | None, name: str | None) -> None:
    """Create a symlink inside the project's ``links/`` folder."""
    root = paths.find_monorepo_root()
    pid = _resolve_project_id(project_id)
    pdir = paths.project_dir(root, pid)
    if not pdir.is_dir():
        raise click.ClickException(f"project {pid!r} not found")

    src = _resolve_target(root, pdir, target)
    if not src.exists():
        raise click.ClickException(f"target does not exist: {src}")

    links = _links_dir(root, pid)
    links.mkdir(parents=True, exist_ok=True)
    link_name = name or src.name
    dest = links / link_name
    if dest.exists() or dest.is_symlink():
        raise click.ClickException(f"link already exists: links/{link_name}")

    # Store as a relative symlink so the link survives a monorepo move.
    rel = os.path.relpath(src, start=dest.parent)
    dest.symlink_to(rel)
    click.echo(f"{pid}: added links/{link_name} -> {rel}")


@link_group.command("ls")
@click.option("--project", "project_id", default=None,
              help="Project id (defaults to the project of the current dir).")
def ls(project_id: str | None) -> None:
    """List the symlinks in the project's ``links/`` folder."""
    root = paths.find_monorepo_root()
    pid = _resolve_project_id(project_id)
    links = _links_dir(root, pid)
    if not links.is_dir():
        click.echo("(no links/ folder)")
        return
    entries = sorted(links.iterdir())
    if not entries:
        click.echo("(empty)")
        return
    for e in entries:
        if e.is_symlink():
            tgt = os.readlink(e)
            live = "ok" if e.exists() else "BROKEN"
            click.echo(f"  {e.name:<30} -> {tgt}  ({live})")
        else:
            click.echo(f"  {e.name:<30} (not a symlink)")


@link_group.command("rm")
@click.argument("name")
@click.option("--project", "project_id", default=None,
              help="Project id (defaults to the project of the current dir).")
def rm(name: str, project_id: str | None) -> None:
    """Remove a symlink from the project's ``links/`` folder."""
    root = paths.find_monorepo_root()
    pid = _resolve_project_id(project_id)
    dest = _links_dir(root, pid) / name
    if not (dest.exists() or dest.is_symlink()):
        raise click.ClickException(f"no such link: links/{name}")
    if dest.is_symlink() or dest.is_file():
        dest.unlink()
    else:
        raise click.ClickException(
            f"refusing to remove non-file links/{name}; handle manually"
        )
    click.echo(f"{pid}: removed links/{name}")
