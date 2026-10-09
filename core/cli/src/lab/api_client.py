"""HTTP access using the owner's existing local CLI credential."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from urllib.parse import urlencode, urlsplit

import click

from lab import paths


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request(method, path, *, body=None, query=(), timeout=30):
    from lab.commands.service import server_port
    import os
    base = os.environ.get('LAB_URL') or f'http://localhost:{server_port()}'
    parsed = urlsplit(base)
    if parsed.scheme not in {'http', 'https'} or parsed.hostname not in {'localhost', '127.0.0.1', '::1'} or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {'', '/'}:
        raise click.ClickException('LAB_URL must be a local Lab origin, such as http://localhost:<port>.')
    route = urlsplit(path)
    if not path.startswith('/api/') or route.scheme or route.netloc or route.fragment or '\\' in path:
        raise click.ClickException('Use an /api/ path from lab api routes.')
    token = paths.read_local_cli_token()
    if not token:
        raise click.ClickException('Local CLI credential unavailable. Start Lab first.')
    url = base.rstrip('/') + path
    if query:
        url += ('&' if route.query else '?') + urlencode(query)
    headers = {'Authorization': f'Bearer {token}', 'X-Lab-CLI-Scope': 'owner',
               'Origin': base.rstrip('/'), 'Accept': 'application/json'}
    data = None if body is None else json.dumps(body).encode()
    if data is not None:
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
    try:
        with urllib.request.build_opener(NoRedirect).open(req, timeout=timeout) as response:
            raw = response.read()
            if 'json' in response.headers.get('Content-Type', ''):
                return json.loads(raw) if raw else None
            return raw
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode(errors='replace')
        try:
            detail = json.loads(raw).get('detail', raw)
        except (ValueError, AttributeError):
            detail = raw
        raise click.ClickException(f'Lab API {exc.code}: {detail}') from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise click.ClickException(f'Cannot reach Lab: {exc}') from exc


def output(value):
    if isinstance(value, bytes):
        click.get_binary_stream('stdout').write(value)
    else:
        click.echo(json.dumps(value, ensure_ascii=False, indent=2))
