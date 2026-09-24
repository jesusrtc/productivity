"""Creation API behavior against an isolated, real tmux server."""
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import time

import pytest


@pytest.fixture
def native_creation_tmux(monorepo, monkeypatch):
    from core.routes import term
    from lab import tmux_sockets

    tmux = shutil.which('tmux')
    if not tmux:
        pytest.skip('tmux is required')
    with tempfile.TemporaryDirectory(prefix='lab-create-api-', dir='/tmp') as directory:
        monkeypatch.setenv('TMUX_TMPDIR', directory)
        monkeypatch.setenv('LAB_TMUX_PREFIX', 'lab-owned-')
        shell = Path(directory, 'owned shell')
        shell.write_text(f'#!{sys.executable}\nimport time\ntime.sleep(60)\n')
        shell.chmod(0o700)
        monkeypatch.setenv('SHELL', str(shell))
        env = term._tmux_child_env()
        socket = 'owned-creation'

        def run(*args, check=True):
            return subprocess.run([tmux, '-L', socket, *args], capture_output=True,
                                  text=True, env=env, check=check, timeout=10)

        server_pid = None
        try:
            run('-f', '/dev/null', 'new-session', '-d', '-s', 'anchor', '/bin/sleep 60')
            server_pid = int(run('display-message', '-p', '#{pid}').stdout)
            tmux_sockets.write_state({
                'version': 1, 'active': socket,
                'generations': [{'name': socket, 'status': 'active', 'created_at': 1}],
            })
            run('set-option', '-g', 'mouse', 'off')
            run('set-option', '-g', 'alternate-screen', 'on')
            run('bind-key', '-T', 'root', 'WheelDownPane', 'display-message', 'original')
            yield run, socket, shell
        finally:
            # Every process and session on this private socket belongs to the
            # fixture. Never enumerate or kill the user's tmux server.
            panes = run('list-panes', '-a', '-F', '#{pane_pid}', check=False)
            pids = {int(pid) for pid in panes.stdout.splitlines()}
            if server_pid is not None:
                pids.add(server_pid)
            run('kill-server', check=False)
            assert run('list-sessions', check=False).returncode != 0
            deadline = time.monotonic() + 3
            while pids:
                for pid in list(pids):
                    try:
                        os.kill(pid, 0)
                    except ProcessLookupError:
                        pids.remove(pid)
                assert not pids or time.monotonic() < deadline, 'Owned processes did not exit'
                if pids:
                    time.sleep(.01)


@pytest.fixture
def native_creation_client(native_creation_tmux, client):
    # Install the private socket environment before the application's lifespan
    # starts, and close the application before tearing the server down.
    return client


def test_native_creation_preserves_shell_scope_options_and_identity(
    native_creation_tmux, native_creation_client, seed_workspace,
):
    run, socket, shell = native_creation_tmux
    workspace = seed_workspace('demo')
    client = native_creation_client
    response = client.post('/api/term/sessions', json={'workspace_id': 'demo', 'kind': 'terminal'})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['name'] == 'lab-owned-demo-bash'
    assert body['tmux_socket'] == socket and body['cwd'] == str(workspace)
    assert shlex.split(body['cmd']) == [str(shell), '-l']
    assert run('display-message', '-p', '-t', body['name'], '#{pane_current_path}').stdout.strip() == str(workspace)
    assert run('show-options', '-v', '-t', body['name'], 'mouse').stdout.strip() == 'on'
    assert run('show-options', '-v', '-t', body['name'], 'alternate-screen').stdout.strip() == 'off'
    assert run('show-options', '-A', '-v', '-t', 'anchor', 'mouse').stdout.strip() == 'off'
    assert run('show-options', '-A', '-v', '-t', 'anchor', 'alternate-screen').stdout.strip() == 'on'
    bindings = run('list-keys', '-T', 'root').stdout
    assert 'WheelDownPane' not in bindings
    assert '#{||:#{pane_in_mode},#{mouse_any_flag}}' in bindings
    assert 'send-keys -M' in bindings and 'copy-mode -e' in bindings
    assert 'copy-mode -eu' not in bindings
    again = client.post('/api/term/sessions', json={'workspace_id': 'demo', 'kind': 'terminal'})
    assert again.status_code == 200 and again.json()['already_running']
    assert again.json()['name'] == body['name']
    saved = client.get('/api/term/sessions/saved?workspace_id=demo')
    assert saved.status_code == 200 and len(saved.json()) == 1
    assert saved.json()[0]['name'] == 'bash'


def test_native_creation_keeps_user_hook_failure_as_api_error(
    native_creation_tmux, native_creation_client, seed_workspace, monorepo,
):
    from core.routes import term
    run, _, _ = native_creation_tmux
    seed_workspace('demo')
    run('set-hook', '-g', 'after-new-session', 'set-option -t missing-hook-target mouse on')
    response = native_creation_client.post('/api/term/sessions', json={
        'workspace_id': 'demo', 'kind': 'terminal',
    })
    assert response.status_code == 500, response.text
    assert 'missing-hook-target' in response.json()['detail']
    # tmux did create a session, but its hook failed. No success metadata or
    # wheel setup should be applied after the failed new-session command.
    name = 'lab-owned-demo-bash'
    assert name in run('list-sessions', '-F', '#{session_name}').stdout.splitlines()
    assert name not in term._load_meta(monorepo)
    assert term._get_workspace_sessions(monorepo, 'demo') == []
    assert run('show-options', '-A', '-v', '-t', name, 'mouse').stdout.strip() == 'off'
    assert run('show-options', '-A', '-v', '-t', name, 'alternate-screen').stdout.strip() == 'on'
    assert 'WheelDownPane' in run('list-keys', '-T', 'root').stdout
