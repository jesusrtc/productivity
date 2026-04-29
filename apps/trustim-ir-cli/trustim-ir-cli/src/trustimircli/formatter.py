import json

import click
from tabulate import tabulate


def format_table(headers, rows, json_output=False):
    if json_output:
        result = []
        for row in rows:
            obj = {}
            for i, h in enumerate(headers):
                obj[h] = row[i] if i < len(row) else ''
            result.append(obj)
        click.echo(json.dumps(result, indent=2))
        return

    if not rows:
        click.echo('No results.')
        return

    click.echo(tabulate(rows, headers=headers, tablefmt='simple'))


def format_detail(title, fields, sections, json_output=False):
    if json_output:
        obj = {'title': title}
        for key, val in fields:
            obj[key] = val
        for heading, content_parts in sections:
            section_data = []
            for part in content_parts:
                if isinstance(part, dict):
                    section_data.append(part)
                else:
                    section_data.append(str(part))
            obj[heading] = section_data
        click.echo(json.dumps(obj, indent=2))
        return

    click.echo(click.style(title, bold=True))
    click.echo()

    max_key_len = max((len(k) for k, _ in fields), default=0)
    for key, val in fields:
        click.echo(f'  {key:<{max_key_len}}  {val}')

    for heading, content_parts in sections:
        click.echo()
        click.echo(click.style(f'--- {heading} ---', bold=True))
        for part in content_parts:
            if isinstance(part, dict):
                # Sub-table
                sub_headers = part.get('headers', [])
                sub_rows = part.get('rows', [])
                click.echo(tabulate(sub_rows, headers=sub_headers, tablefmt='simple'))
            else:
                click.echo(part)


def format_message(message):
    if message:
        click.echo(message)


def format_pagination(pagination):
    parts = []
    if 'total' in pagination:
        parts.append(f'Total: {pagination["total"]}')
    if 'page_info' in pagination:
        parts.append(pagination['page_info'])
    if parts:
        click.echo(click.style(' | '.join(parts), dim=True))


def print_undo_hint():
    click.echo(click.style('Run `ir undo` to revert this change.', dim=True))


def print_error(msg):
    click.echo(click.style(f'Error: {msg}', fg='red'), err=True)
