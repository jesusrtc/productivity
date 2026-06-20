from __future__ import annotations

import click

from lab import agentsync, paths


@click.group(name="agents")
def agents_group() -> None:
    """Cross-tool agent context (AGENTS.md, memory, skills) — one source, symlinks for the rest."""


@agents_group.command("sync")
@click.option("--dry-run", is_flag=True,
              help="Show what would change without touching disk.")
def sync(dry_run: bool) -> None:
    """Make AGENTS.md canonical and (re)link CLAUDE.md, Copilot, and memory.

    Idempotent — safe to run any time (and on every ``make setup``).
    """
    root = paths.find_monorepo_root()
    report = agentsync.sync_all(root, dry_run=dry_run)
    actions = report["actions"]
    if not actions:
        click.echo("nothing to do — already in sync.")
        return
    prefix = "would " if dry_run else ""
    for action in actions:
        click.echo(f"  {prefix}{action}")
    click.echo(f"{'(dry run) ' if dry_run else ''}{len(actions)} action(s).")
