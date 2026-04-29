import click

from trustimircli import client
from trustimircli.parser import (
    parse_detail_table, parse_timeline_table, parse_message, parse_error,
)
from trustimircli.formatter import format_detail, format_table, format_message, print_error
from trustimircli.config import get_env
from trustimircli.undo import load_undo, clear_undo


@click.command('undo')
def undo():
    """Undo the last write action."""
    undo_data = load_undo()
    if not undo_data:
        click.echo('Nothing to undo.')
        return

    action = undo_data.get('action')
    fields = undo_data.get('fields')
    if not action or not isinstance(fields, dict):
        click.echo('Undo data is malformed. Clearing it.', err=True)
        clear_undo()
        return

    saved_env = undo_data.get('env')
    current_env = get_env()
    if saved_env and saved_env != current_env:
        click.echo(
            f'Undo was recorded on {saved_env} but current env is {current_env}. '
            f'Switch with `ir config --env {saved_env}` or pass --force.',
            err=True,
        )
        raise SystemExit(1)

    click.echo(f'Undoing: POST {action}')
    resp = client.post(action, data=fields)

    error = parse_error(resp.text)
    if error:
        print_error(error)
        click.echo('Undo data preserved. You can retry with `ir undo`.', err=True)
        raise SystemExit(1)

    clear_undo()

    msg = parse_message(resp.text)

    # Determine response type based on URL
    if '/timeline' in action:
        headers, rows, incident_title, info_msg = parse_timeline_table(resp.text)
        if info_msg:
            format_message(info_msg)
        elif msg:
            format_message(msg)
        click.echo()
        format_table(headers, rows)
    else:
        title, fields_kv, sections = parse_detail_table(resp.text)
        format_detail(title, fields_kv, sections)
        if msg:
            click.echo()
            format_message(msg)
