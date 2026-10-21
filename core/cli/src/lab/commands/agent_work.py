"""Request and delegated-assignment records; never Objective tasks."""
import click
import sqlite3

from lab import agent_work, terminal_context
from lab.api_client import output


def _call(fn, *args, **kwargs):
    try:
        output(fn(agent_work.identity(), *args, **kwargs))
    except (ValueError, OSError, sqlite3.Error, terminal_context.TerminalContextError) as exc:
        raise click.ClickException(str(exc)) from exc


@click.group('work')
def work():
    """Track this agent's requests and delegated assignments (not Objective tasks)."""


@work.command('start')
@click.option('--title', required=True)
@click.option('--request-file', type=click.File('r', encoding='utf-8'), help='User request or delegated brief; - reads stdin.')
@click.option('--context-file', type=click.File('r', encoding='utf-8'), help='Decisions, constraints and relevant context.')
@click.option('--parent', 'parent_id', type=click.UUID, help='Parent request/assignment ID for a sub-assignment.')
@click.option('--id', 'assignment_id', type=click.UUID, help='Resume the exact assignment supplied by a parent.')
def start(title, request_file, context_file, parent_id, assignment_id):
    _call(agent_work.start, title, request=request_file.read(64001) if request_file else '',
        context=context_file.read(64001) if context_file else '',
        parent_id=str(parent_id) if parent_id else None, assignment_id=str(assignment_id) if assignment_id else None)


@work.command('finish')
@click.option('--summary', default='')
@click.option('--state', type=click.Choice(['finished','attention']), default='finished')
def finish(summary, state):
    _call(agent_work.finish, summary, state)


@work.command('show')
@click.option('--include-children', is_flag=True)
def show(include_children):
    _call(agent_work.history, include_children=include_children)


@click.group('files')
def files():
    """Record/list only files this agent changed, grouped by its request."""


@files.command('record')
@click.argument('paths', nargs=-1, required=True, type=click.Path())
@click.option('--operation', type=click.Choice(['created','modified','deleted','renamed']), default='modified')
@click.option('--previous-path', type=click.Path(), help='Original path for a rename.')
@click.option('--assignment', 'assignment_id', type=click.UUID)
def record(paths, operation, previous_path, assignment_id):
    _call(agent_work.record, paths, operation, previous_path, str(assignment_id) if assignment_id else None)


files.add_command(show, 'list')
