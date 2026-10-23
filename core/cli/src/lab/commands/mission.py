"""The same local mission state used by the agentic workspace UI."""
from __future__ import annotations

import json
import os
from pathlib import Path

import click

from lab import paths, storage
from lab.agentic_store import Store
from lab.api_client import output


def _managed(store):
    from lab.agentic_work import current
    owner = current()
    if owner and owner[0].workspace != store.workspace:
        raise ValueError('A managed run can only modify its own workspace')
    return store.run(owner[1]) if owner else None


@click.group(name='mission')
@click.option('--workspace', 'workspace_id', envvar='LAB_CONTEXT_WORKSPACE')
@click.option('--vault', type=click.Path(path_type=Path, exists=True, file_okay=False))
@click.pass_context
def mission_group(ctx, workspace_id, vault):
    """Inspect and control local agentic missions, tasks, schedules and evidence."""
    root = vault or paths.find_vault_root()
    workspace_id = workspace_id or paths.find_workspace_id_from_pwd(root, Path.cwd())
    folder = paths.workspace_dir(root, workspace_id)
    if storage.read_json(paths.workspace_file(root, workspace_id)).get('kind') != 'agentic':
        raise click.ClickException('This workspace is not agentic; use lab workspace new --kind agentic')
    ctx.obj = Store(folder)


@mission_group.command('ls')
@click.pass_obj
def list_state(store):
    """Read missions, tasks, schedules, memory, messages and execution status."""
    output(store.snapshot())


@mission_group.command('say')
@click.argument('message', required=False)
@click.option('--file', type=click.Path(path_type=Path, exists=True, dir_okay=False))
@click.option('--mission-id')
@click.option('--task-id')
@click.option('--request-id', help='Reuse after a timeout to avoid duplicate messages')
@click.pass_obj
def say(store, message, file, mission_id, task_id, request_id):
    """Send a request to the workspace's one coordinator conversation."""
    if bool(message) == bool(file):
        raise click.UsageError('Choose MESSAGE or --file')
    try:
        if _managed(store):
            raise ValueError('Managed runs cannot submit messages as the user; return a result to the coordinator')
        output(store.message(file.read_text() if file else message, mission_id=mission_id,
                             task_id=task_id, request_id=request_id))
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc


@mission_group.command('apply')
@click.option('--file', required=True, type=click.Path(path_type=Path, exists=True, dir_okay=False))
@click.pass_obj
def apply(store, file):
    """Apply a JSON array of mission/task/schedule actions atomically."""
    try:
        run = _managed(store)
        output(store.apply(json.loads(file.read_text()), actor='executor' if run else 'user', source=run))
    except (ValueError, OSError) as exc:
        raise click.ClickException(str(exc)) from exc


@mission_group.command('task')
@click.argument('task_id')
@click.pass_obj
def task(store, task_id):
    """Inspect results, exact assignments, runs, activity and supporting files."""
    try:
        output(store.detail(task_id))
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc


@mission_group.command('checkpoint')
@click.option('--run-id', envvar='LAB_AGENTIC_RUN', required=True)
@click.option('--file', required=True, type=click.Path(path_type=Path, exists=True, dir_okay=False))
@click.pass_obj
def checkpoint(store, run_id, file):
    """Save an executor's resumable checkpoint while it is working."""
    try:
        run = _managed(store)
        if run and run_id != run['id']:
            raise ValueError('Save only the checkpoint owned by this run')
        store.checkpoint(run_id, file.read_text())
        output({'saved': True, 'run_id': run_id})
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc


@mission_group.command('settings')
@click.option('--file', type=click.Path(path_type=Path, exists=True, dir_okay=False))
@click.pass_obj
def configure(store, file):
    """Read settings, or update from a JSON object (enabled, reminders, capacity)."""
    try:
        if file and _managed(store):
            raise ValueError('Workspace settings are controlled by the user')
        output(store.configure(json.loads(file.read_text())) if file else store.snapshot()['settings'])
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
