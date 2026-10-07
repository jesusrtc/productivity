"""Recovery checks use only owned TTYs and never replace a live connection."""
import json
from pathlib import Path
import shlex
import time
import uuid

import pytest

from core import terminal_automation_lifecycle as lifecycle, terminal_automations
from .test_terminal_automations import _save, _launch
from .test_term_creation_native import native_creation_tmux, native_creation_client  # noqa: F401


def _record(command="sleep 30", **patch):
    return {"command": command, "shell": "/bin/sh", "launch_id": "initial", "updated_at": 0, **patch}


@pytest.mark.parametrize("snapshot,expected", [
    ({10: {"ppid": 1, "stat": "S", "comm": "sh"}}, "stopped"),
    ({10: {"ppid": 1, "stat": "S", "comm": "sh"}, 11: {"ppid": 10, "stat": "S", "comm": "ssh"}}, "running"),
    ({10: {"ppid": 1, "stat": "S", "comm": "sh"}, 11: {"ppid": 10, "stat": "S", "comm": "sh"}, 12: {"ppid": 11, "stat": "T", "comm": "tmux"}}, "running"),
    ({10: {"ppid": 1, "stat": "S", "comm": "sleep"}}, "running"),
    ({10: {"ppid": 1, "stat": "S", "comm": "sh"}, 50: {"ppid": 1, "stat": "S", "comm": "ssh"}}, "stopped"),
    (None, "unknown"), ({}, "unknown"),
])
def test_liveness_uses_owned_descendants_not_browser_attachment(snapshot, expected):
    state = lifecycle.status(_record(), {"pane_pid": 10, "attached": False}, True, snapshot)
    assert state["state"] == expected
    assert state["can_relaunch"] == (expected == "stopped")


def test_missing_unknown_starting_multiple_panes_and_background_probe(tmp_path):
    assert lifecycle.status(_record(), None, True, None)["can_relaunch"]
    assert not lifecycle.status(_record(), None, False, None)["can_relaunch"]
    assert not lifecycle.status(_record(updated_at=time.time()), None, True, None)["can_relaunch"]
    idle = {10: {"ppid": 1, "stat": "S", "comm": "sh"}}
    assert not lifecycle.status(_record(), {"pane_pid": 10, "pane_count": 2}, True, idle)["can_relaunch"]
    assert not lifecycle.status(_record(), {"pane_dead": True, "pane_count": 2}, True, idle)["can_relaunch"]
    for exit_code, expected in [(0, "running"), (1, "stopped"), (2, "unknown")]:
        state = lifecycle.status(_record(cwd=str(tmp_path), health_command=f"exit {exit_code}"), None, True, None)
        assert state["state"] == expected


def test_legacy_adoption_is_exact_private_and_never_executes(tmp_path):
    logical = "automation-" + "a" * 32 + "-1"
    command = "printf '%s' 'literal $(false)'\nexit 7"
    row = {"workspace_id": "demo", "logical_name": logical, "cwd": str(tmp_path),
           "cmd": shlex.join(terminal_automations.shell_command('/bin/sh', tmp_path, command))}
    adopted = lifecycle.adopt_legacy(tmp_path, {'one': row}, 'demo')
    assert adopted[logical]['command'] == command
    path = tmp_path / '.lab/terminal-automation-runs.json'
    assert path.stat().st_mode & 0o777 == 0o600
    assert lifecycle.adopt_legacy(tmp_path, {'one': {**row, 'cmd': 'ssh somewhere'}}, 'demo') == adopted
    assert not lifecycle.adopt_legacy(tmp_path / 'other', {'one': row}, 'other')


def test_guidelines_preserve_literal_whitespace_and_reject_empty_text():
    text = "  python app.py\n\n"
    assert terminal_automations.Guideline(title="  Debugger  ", text=text).model_dump() == {
        "title": "Debugger", "text": text,
    }
    with pytest.raises(ValueError):
        terminal_automations.Guideline(text="  \n")


def _status(client, logical, expected=None):
    deadline = time.monotonic() + 7
    while True:
        response = client.get('/api/term/automations/status?workspace_id=demo')
        assert response.status_code == 200, response.text
        row = next(row for row in response.json()['sessions'] if row['logical_name'] == logical)
        if expected is None or row['automation']['state'] == expected:
            return row
        assert time.monotonic() < deadline, row
        time.sleep(.05)


def _recover(client, rows, **patch):
    return client.post('/api/term/automations/relaunch', json={
        'workspace_id': 'demo', 'request_id': str(uuid.uuid4()),
        'targets': [{'logical_name': row['logical_name'], 'launch_id': row['automation']['launch_id']} for row in rows],
        **patch,
    })


def test_native_recovery_preserves_running_work_guidelines_identity_and_previous_logs(
    native_creation_tmux, native_creation_client, seed_workspace, monkeypatch,
):
    run, _, _ = native_creation_tmux
    monkeypatch.setenv('SHELL', '/bin/sh'); run('set-option', '-g', 'default-shell', '/bin/sh')
    client = native_creation_client; folder = seed_workspace()
    parent = client.post('/api/term/sessions', json={'workspace_id': 'demo', 'kind': 'terminal'}).json()
    guides = [{'title': 'Debugger', 'text': 'python -m debugpy app.py'}, {'title': 'Normal', 'text': 'python app.py'}]
    catalog = _save(client, 'demo', [
        {'label': 'Stopped', 'command': "printf 'old log\\n'; printf x >> count; exit 7", 'guidelines': guides},
        {'label': 'Running', 'command': 'sleep 60'},
    ])
    rows = client.post('/api/term/automations/launch', json=_launch(parent, catalog)).json()['sessions']
    stopped = _status(client, rows[0]['logical_name'], 'stopped')
    alive = _status(client, rows[1]['logical_name'], 'running')
    assert stopped['automation']['guidelines'] == guides
    pid = run('display-message', '-p', '-t', alive['name'], '#{pane_pid}').stdout
    body = {'workspace_id': 'demo', 'request_id': str(uuid.uuid4()), 'targets': [
        {'logical_name': row['logical_name'], 'launch_id': row['automation']['launch_id']} for row in [stopped, alive]]}
    response = client.post('/api/term/automations/relaunch', json=body)
    assert response.status_code == 200, response.text
    result = response.json()
    assert len(result['sessions']) == 1 and len(result['skipped']) == 1 and not result['errors']
    assert result['sessions'][0]['session_id'] == rows[0]['session_id']
    _status(client, stopped['logical_name'], 'stopped')
    assert (folder / 'count').read_text() == 'xx'
    assert run('display-message', '-p', '-t', alive['name'], '#{pane_pid}').stdout == pid
    assert any('old log' in path.read_text() for path in (folder / '.lab/terminal-automation-logs').glob('*.txt'))
    # A retried HTTP request and a stale second browser click cannot replay it.
    assert not client.post('/api/term/automations/relaunch', json=body).json()['sessions']
    assert not _recover(client, [stopped]).json()['sessions']
    assert (folder / 'count').read_text() == 'xx'
    assert client.post('/api/term/automations/relaunch', json={**body, 'workspace_id': 'other'}).status_code == 404
    assert client.delete('/api/term/sessions/' + stopped['name']).status_code == 200
    missing = _status(client, stopped['logical_name'], 'stopped')
    assert missing['automation_missing']
    restored = _recover(client, [missing]).json()
    assert len(restored['sessions']) == 1 and not restored['errors']
    _status(client, stopped['logical_name'], 'stopped')
    assert (folder / 'count').read_text() == 'xxx'
    assert restored['sessions'][0]['session_id'] == rows[0]['session_id']
    saved = json.loads((folder / 'workspace.json').read_text())['sessions']
    assert all('startup_command' not in row for row in saved)
    assert not (folder / 'app.py').exists()  # guidelines were not executed


def test_native_nested_tmux_detach_reconnects_existing_inner_session(
    native_creation_tmux, native_creation_client, seed_workspace, monkeypatch,
):
    run, socket, _ = native_creation_tmux
    monkeypatch.setenv('SHELL', '/bin/sh'); run('set-option', '-g', 'default-shell', '/bin/sh')
    client = native_creation_client; seed_workspace()
    # The nested server is the same owned test socket; the inner session and
    # outer automation pane are independent. Never inspect the user's server.
    run('new-session', '-d', '-s', 'inner', 'sleep 60')
    inner_pid = run('display-message', '-p', '-t', 'inner', '#{pane_pid}').stdout
    parent = client.post('/api/term/sessions', json={'workspace_id': 'demo', 'kind': 'terminal'}).json()
    command = f'TMUX= tmux -L {shlex.quote(socket)} attach-session -t inner'
    catalog = _save(client, 'demo', [{'label': 'Nested', 'command': command}])
    row = client.post('/api/term/automations/launch', json=_launch(parent, catalog)).json()['sessions'][0]
    alive = _status(client, row['logical_name'], 'running')
    assert not _recover(client, [alive]).json()['sessions']
    run('detach-client', '-s', 'inner')
    stopped = _status(client, row['logical_name'], 'stopped')
    assert stopped['automation']['kind'] == 'tmux'
    response = _recover(client, [stopped]).json()
    assert len(response['sessions']) == 1 and not response['errors'], response
    _status(client, row['logical_name'], 'running')
    assert run('display-message', '-p', '-t', 'inner', '#{pane_pid}').stdout == inner_pid


def test_native_lost_registry_and_manual_work_prevent_stale_recovery(
    native_creation_tmux, native_creation_client, seed_workspace, monorepo, monkeypatch,
):
    from core.routes import term
    run, _, _ = native_creation_tmux
    monkeypatch.setenv('SHELL', '/bin/sh'); run('set-option', '-g', 'default-shell', '/bin/sh')
    client = native_creation_client; folder = seed_workspace()
    parent = client.post('/api/term/sessions', json={'workspace_id': 'demo', 'kind': 'terminal'}).json()
    catalog = _save(client, 'demo', [{'label': 'Manual work', 'command': 'printf x >> count'}])
    row = client.post('/api/term/automations/launch', json=_launch(parent, catalog)).json()['sessions'][0]
    stopped = _status(client, row['logical_name'], 'stopped')
    # A user can start work after the UI received a stopped status. Recovery
    # must check again, including when the runtime registry needs rebuilding.
    run('send-keys', '-t', row['name'], 'sleep 60', 'Enter')
    _status(client, row['logical_name'], 'running')
    pid = run('display-message', '-p', '-t', row['name'], '#{pane_pid}').stdout
    term._save_meta(monorepo, {})
    alive = _status(client, row['logical_name'], 'running')
    assert not alive['automation_missing']
    result = _recover(client, [stopped]).json()
    assert not result['sessions'] and len(result['skipped']) == 1 and not result['errors']
    assert (folder / 'count').read_text() == 'x'
    assert run('display-message', '-p', '-t', row['name'], '#{pane_pid}').stdout == pid
