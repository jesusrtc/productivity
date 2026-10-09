"""Objectives live in their own folders; workspace/task metadata stays intact."""
import json
from pathlib import Path
import click
from lab import objectives, paths
from lab.commands._helpers import resolve_workspace_id


@click.group(name='objective')
def objective_group():
    """Manage problem-focused objectives inside a workspace."""


@objective_group.command('ls')
@click.option('--workspace', default=None)
def list_objectives(workspace):
    """Discover Objective files and print their owned document content."""
    try:
        click.echo(json.dumps(objectives.payload(paths.find_monorepo_root(), resolve_workspace_id(workspace)), indent=2))
    except (ValueError, OSError, KeyError) as exc:
        raise click.ClickException(str(exc)) from exc


@objective_group.command('migrate')
@click.option('--workspace', default=None)
@click.option('--apply', 'apply_changes', is_flag=True, help='Write Objective files and preserve a byte-identical legacy backup.')
def migrate(workspace, apply_changes):
    """Preview or convert the old registry to per-folder .objective.json files."""
    try:
        result = objectives.migrate(paths.find_monorepo_root(), resolve_workspace_id(workspace), apply=apply_changes)
        click.echo(json.dumps(result, indent=2))
    except (ValueError, OSError, KeyError) as exc:
        raise click.ClickException(str(exc)) from exc


@objective_group.command('apply')
@click.option('--workspace', default=None)
@click.option('--file', 'action_file', type=click.Path(exists=True, path_type=Path), required=True)
@click.option('--expected', default=None, help='Require the revision returned by objective ls; reject stale changes.')
def apply(workspace, action_file, expected):
    """Apply one JSON objective action through Lab's locked store.

    \b
    Asset grouping actions:
      asset-group-create
      asset-group-member
      asset-group-rename
      asset-group-ungroup
      asset-order

    Read `lab context objectives` for action fields and examples.
    """
    try:
        result = objectives.mutate(paths.find_monorepo_root(), resolve_workspace_id(workspace), json.loads(action_file.read_text()), expected=expected)
        click.echo(json.dumps(result, indent=2))
    except (ValueError, OSError, KeyError) as exc:
        raise click.ClickException(str(exc)) from exc
