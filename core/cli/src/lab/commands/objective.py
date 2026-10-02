"""Objectives use their own registry; existing workspace/task metadata stays intact."""
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
    """Print the objective registry and owned document content."""
    click.echo(json.dumps(objectives.payload(paths.find_monorepo_root(), resolve_workspace_id(workspace)), indent=2))


@objective_group.command('apply')
@click.option('--workspace', default=None)
@click.option('--file', 'action_file', type=click.Path(exists=True, path_type=Path), required=True)
def apply(workspace, action_file):
    """Apply one JSON objective action through Lab's locked store."""
    try:
        result = objectives.mutate(paths.find_monorepo_root(), resolve_workspace_id(workspace), json.loads(action_file.read_text()))
        click.echo(json.dumps(result, indent=2))
    except (ValueError, OSError, KeyError) as exc:
        raise click.ClickException(str(exc)) from exc
