"""Owned echo terminals for native tab-switch measurements."""
from contextlib import contextmanager
import json
from pathlib import Path
import shlex
import subprocess
import sys
import urllib.request
from urllib.parse import quote, urlparse
import uuid


@contextmanager
def terminal_tab_fixture(base_url, cookie, workspace, count=6):
    workspace = Path(workspace).resolve()
    if (urlparse(base_url).hostname != '127.0.0.1'
            or len(workspace.parents) < 3
            or not workspace.parents[2].name.startswith('lab-navigation-')
            or workspace.parts[-3:] != ('vault', 'workspaces', 'alpha')):
        raise ValueError('Terminal tab measurements require the disposable navigation fixture')
    from core.routes.term import _tmux_command, _tmux_find_session_socket
    from lab_terminal_latency import echo_program

    def request(route, method, data=None):
        req = urllib.request.Request(base_url + route, method=method,
            data=None if data is None else json.dumps(data).encode(),
            headers={'Cookie': 'lab_session=' + cookie, 'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.load(response)

    owned = []
    try:
        for index in range(count):
            token = uuid.uuid4().hex
            created = request('/api/term/sessions', 'POST', {
                'kind': 'terminal', 'cwd': str(workspace), 'workspace_id': workspace.name,
                'name': 'latency-tab-' + token,
            })
            entry = {'name': created['name'], 'marker': f'tab-{index}-' + token[:16]}
            owned.append(entry)
            socket = _tmux_find_session_socket(entry['name'])
            if not socket:
                raise RuntimeError('New fixture terminal has no tmux socket')
            command = shlex.join([sys.executable, '-u', '-c', echo_program(entry['marker'])])
            subprocess.run(_tmux_command(socket, 'respawn-pane', '-k', '-t', entry['name'], command),
                           check=True, timeout=10, stdout=subprocess.DEVNULL)
        yield owned
    finally:
        errors = []
        for entry in owned:
            try:
                request('/api/term/sessions/' + quote(entry['name'], safe='') + '?purge=true', 'DELETE')
            except Exception as error:
                errors.append(str(error))
        if errors:
            raise RuntimeError('Fixture terminal cleanup failed: ' + '; '.join(errors))
        print(f'Removed {len(owned)} benchmark terminals.', file=sys.stderr)
