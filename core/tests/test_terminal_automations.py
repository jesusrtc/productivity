"""Saved recipes and launch endpoints never touch the production tmux server."""
import json
import shlex
import subprocess
import time
import uuid

import pytest
from fastapi import HTTPException

from core import terminal_automations
from .test_term_routes import isolated_prefix  # noqa: F401
from .test_term_creation_native import native_creation_tmux, native_creation_client  # noqa: F401


def _save(client, workspace, steps):
    current = client.get('/api/term/automations', params={'workspace_id': workspace}).json()
    response = client.post('/api/term/automations', json={
        'workspace_id': workspace, 'revision': current['revision'],
        'automations': [{'id': 'dev', 'name': 'Development', 'steps': steps}],
    })
    assert response.status_code == 200, response.text
    return response.json()


def _launch(parent, catalog, **patch):
    return {'workspace_id': 'demo', 'parent': parent['name'], 'automation_id': 'dev',
            'revision': catalog['revision'], 'run_id': str(uuid.uuid4()), **patch}


def test_recipes_are_workspace_owned_versioned_and_never_launch_on_save(client, seed_workspace, isolated_prefix):
    folder = seed_workspace()
    seed_workspace('other')
    original = client.get('/api/term/automations?workspace_id=demo').json()
    catalog = _save(client, 'demo', [{'label': 'Frontend', 'command': 'npm run dev', 'cwd': 'frontend'}])
    assert client.get('/api/term/sessions?workspace_id=demo').json() == []
    assert client.get('/api/term/automations?workspace_id=other').json()['automations'] == []
    stored = json.loads((folder / '.lab/terminal-automations.json').read_text())
    assert list(stored) == ['automations']
    assert stored['automations'] == catalog['automations']
    assert client.post('/api/term/automations', json={
        'workspace_id': 'demo', 'revision': original['revision'], 'automations': [],
    }).status_code == 409
    assert client.get('/api/term/automations?workspace_id=demo').json() == catalog
    assert client.post('/api/term/automations', json={
        'workspace_id': 'demo', 'revision': catalog['revision'],
        'automations': [{'id': 'empty', 'name': 'Empty', 'steps': []}],
    }).status_code == 422
    assert client.post('/api/term/automations', json={
        'workspace_id': 'demo', 'revision': catalog['revision'], 'automations': [],
    }).json()['automations'] == []


def test_launch_preflights_every_path_uses_fixed_parent_folder_and_deduplicates(client, seed_workspace, isolated_prefix):
    folder = seed_workspace()
    parent_folder = folder / "checkout with ' quotes"
    (parent_folder / 'frontend').mkdir(parents=True)
    parent = client.post('/api/term/sessions', json={
        'workspace_id': 'demo', 'kind': 'terminal', 'cwd': str(parent_folder), 'name': 'parent',
    }).json()
    steps = [{'label': 'Logs', 'command': "printf 'logs\\n'"},
             {'label': 'Frontend', 'command': 'npm run dev', 'cwd': 'frontend'}]
    catalog = _save(client, 'demo', steps)
    body = _launch(parent, catalog)
    preview = client.post('/api/term/automations/launch', json={**body, 'preview': True})
    assert preview.status_code == 200, preview.text
    assert [row['cwd'] for row in preview.json()['steps']] == [str(parent_folder), str(parent_folder / 'frontend')]
    assert len(client.get('/api/term/sessions?workspace_id=demo').json()) == 1
    result = client.post('/api/term/automations/launch', json=body)
    assert result.status_code == 200, result.text
    rows = result.json()['sessions']
    assert [row['label'] for row in rows] == ['Logs', 'Frontend']
    assert [row['cwd'] for row in rows] == [str(parent_folder), str(parent_folder / 'frontend')]
    assert all(row['kind'] == 'terminal' and row['name'] != parent['name'] for row in rows)
    repeated = client.post('/api/term/automations/launch', json=body).json()['sessions']
    assert [row['name'] for row in repeated] == [row['name'] for row in rows]
    assert all(row['already_running'] for row in repeated)
    assert len(client.get('/api/term/sessions?workspace_id=demo').json()) == 3
    saved = json.loads((folder / 'workspace.json').read_text())['sessions']
    assert all('startup_command' not in row for row in saved)
    assert all('cmd' not in row for row in saved)
    broken = _save(client, 'demo', [steps[0], {**steps[1], 'cwd': 'missing'}])
    assert client.post('/api/term/automations/launch', json=_launch(parent, broken)).status_code == 400
    assert len(client.get('/api/term/sessions?workspace_id=demo').json()) == 3
    assert client.post('/api/term/automations/launch', json=_launch(parent, catalog)).status_code == 409


def test_launch_rejects_cross_workspace_parent_and_reports_partial_failure(client, seed_workspace, isolated_prefix, monkeypatch):
    seed_workspace()
    seed_workspace('other')
    parent = client.post('/api/term/sessions', json={'workspace_id': 'demo', 'kind': 'terminal'}).json()
    catalog = _save(client, 'demo', [{'label': 'One', 'command': 'printf one'}, {'label': 'Two', 'command': 'printf two'}])
    other = _save(client, 'other', [{'label': 'Other', 'command': 'printf other'}])
    assert client.post('/api/term/automations/launch', json=_launch(parent, other, workspace_id='other')).status_code == 404
    import core.routes.term as term
    original = term.create_session
    def fail_second(body, request):
        if body.label == 'Two':
            raise HTTPException(500, 'sample spawn failure')
        return original(body, request)
    monkeypatch.setattr(term, 'create_session', fail_second)
    result = client.post('/api/term/automations/launch', json=_launch(parent, catalog)).json()
    assert len(result['sessions']) == 1 and result['sessions'][0]['label'] == 'One'
    assert result['error'] == 'Two: sample spawn failure'
    assert len(client.get('/api/term/sessions?workspace_id=demo').json()) == 2


def test_command_wrapper_preserves_multiline_quoting_exit_logs_and_cwd(tmp_path):
    folder = tmp_path / "spaces and 'quotes"
    folder.mkdir()
    command = "printf '%s\\n' 'literal $(false) ; quoted'\npwd\nprintf 'saved' > result.txt\nexit 7"
    result = subprocess.run(terminal_automations.shell_command('/bin/sh', folder, command),
                            stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=5)
    assert result.returncode == 0
    assert 'literal $(false) ; quoted' in result.stdout
    assert str(folder) in result.stdout
    assert '[Automation exited: 7]' in result.stdout
    assert (folder / 'result.txt').read_text() == 'saved'


def test_explicitly_borrowed_document_parent_keeps_its_owner_and_folder(client, seed_workspace, isolated_prefix, monkeypatch):
    seed_workspace()
    other = seed_workspace('other')
    parent = client.post('/api/term/sessions', json={'workspace_id': 'other', 'kind': 'terminal'}).json()
    catalog = _save(client, 'demo', [{'label': 'Logs', 'command': 'printf logs'}])
    from core import workspace_documents
    monkeypatch.setattr(workspace_documents, 'borrowed_terminals', lambda *_: [{
        **parent, 'logical_name': '@document:' + parent['name'],
        'document_source': {'workspace_id': 'other', 'logical_name': parent['logical_name']},
    }])
    rows = client.post('/api/term/automations/launch', json=_launch(parent, catalog)).json()['sessions']
    assert len(rows) == 1 and rows[0]['cwd'] == str(other) and rows[0]['workspace_id'] == 'demo'
    assert client.get('/api/term/sessions?workspace_id=other').json()[0]['name'] == parent['name']


@pytest.mark.parametrize('owner', ['workflow', 'objective', 'task'])
def test_launched_children_can_save_context_without_taking_primary_ownership(client, seed_workspace, isolated_prefix, owner):
    seed_workspace()
    def action(patch):
        response = client.post('/api/objectives', json={'workspace_id':'demo', 'action':patch})
        assert response.status_code == 200, response.text
        return response.json()
    data = action({'type':'create', 'name':'Demo objective'})
    oid = data['objectives'][0]['id']
    data = action({'type':'task', 'objective_id':oid, 'title':'Development'})
    task_id = data['objectives'][0]['tasks'][0]['id']
    parent = client.post('/api/term/sessions', json={'workspace_id':'demo', 'kind':'terminal'}).json()
    target = {'main':'workflow'} if owner == 'workflow' else {'objective_id':oid, **({'main':'objective'} if owner == 'objective' else {'task_id':task_id})}
    before = action({'type':'terminal', 'session_id':parent['session_id'], **target})
    catalog = _save(client, 'demo', [{'label':'Logs', 'command':'printf logs'}])
    child = client.post('/api/term/automations/launch', json=_launch(parent, catalog)).json()['sessions'][0]
    association = {'view':'workflow'} if owner == 'workflow' else {'objective_id':oid, 'view':'tasks'}
    after = action({'type':'terminal', 'session_id':child['session_id'], **association})
    assert after['terminal_links'][parent['session_id']] == before['terminal_links'][parent['session_id']]
    assert {key:value for key,value in after['terminal_links'][child['session_id']].items() if value is not None} == association
    assert 'main' not in after['terminal_links'][child['session_id']]
    assert 'task_id' not in after['terminal_links'][child['session_id']]


def test_native_launch_runs_once_in_tmux_and_keeps_exited_logs(native_creation_tmux, native_creation_client, seed_workspace, monkeypatch):
    run, socket, _ = native_creation_tmux
    monkeypatch.setenv('SHELL', '/bin/sh')
    # The shared creation fixture originally sets a sleeping fake default shell.
    run('set-option', '-g', 'default-shell', '/bin/sh')
    client = native_creation_client
    folder = seed_workspace()
    (folder / 'frontend').mkdir()
    parent = client.post('/api/term/sessions', json={'workspace_id': 'demo', 'kind': 'terminal'}).json()
    catalog = _save(client, 'demo', [
        {'label': 'Build', 'command': "printf 'build log\\n'; printf x >> count; exit 4"},
        {'label': 'Frontend', 'cwd': 'frontend', 'command': "printf 'frontend log\\n'; pwd"},
    ])
    body = _launch(parent, catalog)
    response = client.post('/api/term/automations/launch', json=body)
    assert response.status_code == 200, response.text
    rows = response.json()['sessions']
    assert len(rows) == 2 and all(row['tmux_socket'] == socket for row in rows)
    deadline = time.monotonic() + 5
    while True:
        logs = [run('capture-pane', '-p', '-J', '-t', row['name'], '-S', '-100').stdout for row in rows]
        if '[Automation exited: 4]' in logs[0] and '[Automation exited: 0]' in logs[1]:
            break
        assert time.monotonic() < deadline, logs
        time.sleep(.02)
    assert 'build log' in logs[0] and 'frontend log' in logs[1]
    assert str(folder / 'frontend') in logs[1]
    assert (folder / 'count').read_text() == 'x'
    repeated = client.post('/api/term/automations/launch', json=body).json()['sessions']
    assert all(row['already_running'] for row in repeated)
    assert (folder / 'count').read_text() == 'x'
    # The completed build is an ordinary interactive child now, with its logs.
    run('send-keys', '-t', rows[0]['name'], 'printf usable-shell', 'Enter')
    deadline = time.monotonic() + 3
    while 'usable-shell' not in run('capture-pane', '-p', '-t', rows[0]['name']).stdout:
        assert time.monotonic() < deadline
        time.sleep(.02)
    assert client.delete('/api/term/sessions/' + rows[0]['name']).status_code == 200
    restored = client.post('/api/term/sessions', json={
        'workspace_id':'demo', 'kind':'terminal', 'name':rows[0]['logical_name'],
    }).json()
    assert shlex.split(restored['cmd']) == ['/bin/sh', '-l']
    assert restored['cwd'] == str(folder) and (folder / 'count').read_text() == 'x'
