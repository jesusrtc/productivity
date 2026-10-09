"""CLI access to all server-side operations, including future UI endpoints."""
from __future__ import annotations

import json
from pathlib import Path

import click

from lab.api_client import output, request


@click.group(name='api')
def api_group():
    """Discover and call every Lab UI API with its existing validation."""


@api_group.command('routes')
@click.option('--search', default='', help='Match path, description or operation name.')
@click.option('--method', type=click.Choice(['GET', 'POST', 'PATCH', 'PUT', 'DELETE', 'HEAD', 'OPTIONS']), default=None)
@click.option('--json', 'as_json', is_flag=True, help='Include complete parameter and body schemas.')
def routes(search, method, as_json):
    catalogue = request('GET', '/api/commands')
    rows = [{'method': verb.upper(), 'path': path, **operation}
            for path, operations in catalogue['paths'].items()
            for verb, operation in operations.items()
            if verb.upper() in {'GET', 'POST', 'PATCH', 'PUT', 'DELETE', 'HEAD', 'OPTIONS'}
            and (not method or verb.upper() == method)
            and search.lower() in (path + ' ' + json.dumps(operation)).lower()]
    if as_json:
        output({'operations': rows, 'components': catalogue.get('components', {})})
    else:
        for row in rows:
            click.echo(f"{row['method']:6} {row['path']}  {row.get('summary', '')}")


@api_group.command('describe')
@click.argument('method', type=click.Choice(['GET', 'POST', 'PATCH', 'PUT', 'DELETE', 'HEAD', 'OPTIONS'], case_sensitive=False))
@click.argument('path')
def describe(method, path):
    catalogue = request('GET', '/api/commands')
    operation = catalogue['paths'].get(path, {}).get(method.lower())
    if operation is None:
        raise click.ClickException('Unknown operation. Run lab api routes.')
    output({'method': method.upper(), 'path': path, **operation, 'components': catalogue.get('components', {})})


@api_group.command('call')
@click.argument('method', type=click.Choice(['GET', 'POST', 'PATCH', 'PUT', 'DELETE', 'HEAD', 'OPTIONS'], case_sensitive=False))
@click.argument('path')
@click.option('--json', 'json_body', default=None, help='JSON request body; use --body-file for larger inputs.')
@click.option('--body-file', type=click.File('r'), default=None, help='JSON file, or - for stdin.')
@click.option('--query', multiple=True, help='Query parameter KEY=VALUE; repeat as needed.')
@click.option('--output', 'output_file', type=click.Path(path_type=Path), default=None, help='Save the response to a file, including binary downloads.')
@click.option('--timeout', type=click.IntRange(1, 3600), default=30, show_default=True)
def call(method, path, json_body, body_file, query, output_file, timeout):
    if json_body is not None and body_file is not None:
        raise click.ClickException('Use one of --json or --body-file.')
    try:
        body = json.loads(body_file.read() if body_file else json_body) if body_file or json_body is not None else None
    except ValueError as exc:
        raise click.ClickException(f'Invalid JSON: {exc}') from exc
    params = []
    for item in query:
        key, separator, value = item.partition('=')
        if not key or not separator:
            raise click.ClickException('--query must use KEY=VALUE.')
        params.append((key, value))
    result = request(method, path, body=body, query=params, timeout=timeout)
    if output_file:
        output_file.write_bytes(result if isinstance(result, bytes) else (json.dumps(result, ensure_ascii=False, indent=2)+'\n').encode())
        click.echo(str(output_file))
    else:
        output(result)
