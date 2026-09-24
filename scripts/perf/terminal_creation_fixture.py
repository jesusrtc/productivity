"""A configured echo shell for native creation in the disposable Lab vault."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.request
from urllib.parse import quote, urlparse
import uuid


@contextmanager
def terminal_creation_fixture(base_url, cookie, workspace):
    workspace = Path(workspace).resolve()
    if (urlparse(base_url).hostname != '127.0.0.1' or len(workspace.parents) < 3
            or not workspace.parents[2].name.startswith('lab-navigation-')
            or workspace.parts[-3:] != ('vault', 'workspaces', 'alpha')):
        raise ValueError('Terminal creation requires the disposable navigation fixture')
    from core.routes.term import _tmux_command, _tmux_find_session_socket, _tmux_session_info
    from lab_terminal_latency import echo_program

    base = workspace.parents[2]
    processes = base / 'terminal-create-processes'
    processes.mkdir()
    marker = 'created-' + uuid.uuid4().hex
    shell = base / 'terminal-create-shell'
    shell.write_text(f'#!{sys.executable}\n'
                     'import json,os\nfrom pathlib import Path\n'
                     f'Path({str(processes)!r}, str(os.getpid())+".json").write_text('
                     'json.dumps({"pid":os.getpid(),"cwd":os.getcwd()}))\n'
                     + echo_program(marker) + '\n')
    shell.chmod(0o700)

    def request(route, method='GET', data=None):
        req = urllib.request.Request(base_url + route, method=method,
            data=None if data is None else json.dumps(data).encode(),
            headers={'Cookie': 'lab_session=' + cookie, 'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.load(response)

    route = '/api/term/sessions?workspace_id=alpha'
    if request(route):
        raise RuntimeError('Creation fixture must start with no terminal sessions')
    report = {'marker': marker, 'shell': str(shell), 'processes': [], 'sessions': [], 'cleaned': False}
    previous_shell = os.environ.get('SHELL')
    os.environ['SHELL'] = str(shell)
    try:
        yield report
    finally:
        try:
            request('/api/ui/term-autospawn', 'POST', {'workspace_id': 'alpha', 'enabled': False})
            errors = []
            for row in request(route):
                name = row.get('name', '')
                if (not name.startswith(base.name + '-') or row.get('kind') != 'terminal'
                        or Path(row.get('cwd', '')).resolve() != workspace
                        or str(shell) not in row.get('cmd', '')):
                    errors.append('Unexpected session preserved: ' + name)
                    continue
                report['sessions'].append({'name': name, 'logical_name': row['logical_name']})
                socket = _tmux_find_session_socket(name)
                if socket:
                    pid = int(subprocess.check_output(_tmux_command(socket, 'display-message', '-p',
                              '-t', name, '#{pane_pid}'), text=True, timeout=5).strip())
                    source = processes / f'{pid}.json'
                    if not source.exists():
                        errors.append('Owned shell did not record its process: ' + name)
                    else:
                        info = json.loads(source.read_text())
                        if info != {'pid': pid, 'cwd': str(workspace)}:
                            errors.append('Owned shell identity mismatch: ' + name)
                        # This file is written by the unchanged owned shell
                        # before tty setup/its first output. Read its existing
                        # timestamp during cleanup, not on the measured path.
                        report['processes'].append({**info, 'name': name,
                            'processRecordEpoch': source.stat().st_mtime_ns / 1_000_000})
                request('/api/term/sessions/' + quote(name, safe='') + '?purge=true', 'DELETE')
                # has-session accepts prefixes: removed bash-2 may match bash-20.
                # The normal list helper checks the full session name.
                if _tmux_session_info(name):
                    errors.append('Owned session survived cleanup: ' + name)
            if request(route) or request('/api/term/sessions/saved?workspace_id=alpha'):
                errors.append('Creation fixture still has live or saved terminals')
            report['cleaned'] = not errors
            if errors:
                raise RuntimeError('; '.join(errors))
            print(f"Removed {len(report['sessions'])} created benchmark terminals.", file=sys.stderr)
        finally:
            if previous_shell is None:
                os.environ.pop('SHELL', None)
            else:
                os.environ['SHELL'] = previous_shell
