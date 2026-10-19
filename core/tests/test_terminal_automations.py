"""Saved recipes and launch endpoints never touch the production tmux server."""
import json
import shlex
import subprocess
from concurrent.futures import ThreadPoolExecutor
import threading
import time
import uuid

import pytest
from fastapi import HTTPException

from core import terminal_automations
from .test_term_routes import isolated_prefix  # noqa: F401
from .test_term_creation_native import native_creation_tmux, native_creation_client  # noqa: F401


@pytest.fixture(autouse=True)
def launch_waits(monkeypatch):
    waits = []
    monkeypatch.setattr(terminal_automations, 'sleep', waits.append)
    return waits


def _save(client, workspace, steps, **options):
    current = client.get('/api/term/automations', params={'workspace_id': workspace}).json()
    response = client.post('/api/term/automations', json={
        'workspace_id': workspace, 'revision': current['revision'],
        'automations': [{'id': 'dev', 'name': 'Development', 'steps': steps, **options}],
    })
    assert response.status_code == 200, response.text
    return response.json()


def _wip_target(client, workspace='demo'):
    data = client.get('/api/objectives', params={'workspace_id': workspace}).json()
    for objective in data['objectives']:
        for task in objective['tasks']:
            if task.get('status') == 'in_progress':
                return {'objective_id': objective['id'], 'task_id': task['id']}
    def action(value):
        response = client.post('/api/objectives', json={'workspace_id': workspace, 'action': value})
        assert response.status_code == 200, response.text
        return response.json()
    if not data['objectives']:
        data = action({'type': 'create', 'name': 'Automation work'})
    objective = data['objectives'][0]
    data = action({'type': 'task', 'objective_id': objective['id'], 'title': 'Run automation'})
    task = next(o for o in data['objectives'] if o['id'] == objective['id'])['tasks'][-1]
    action({'type': 'task-update', 'objective_id': objective['id'], 'task_id': task['id'], 'status': 'in_progress'})
    return {'objective_id': objective['id'], 'task_id': task['id']}


def _launch(client, parent, catalog, **patch):
    return {**_wip_target(client, patch.get('workspace_id', 'demo')), 'workspace_id': 'demo', 'parent': parent['name'], 'automation_id': 'dev',
            'revision': catalog['revision'], 'run_id': str(uuid.uuid4()), **patch}


def test_expired_task_terminal_refuses_automatic_restore_and_explicit_reopen_clears_marker(
    client, seed_workspace, monorepo, isolated_prefix,
):
    from core.routes import term
    seed_workspace()
    body = {'workspace_id': 'demo', 'kind': 'terminal', 'name': 'retired'}
    created = client.post('/api/term/sessions', json=body)
    assert created.status_code == 200, created.text
    saved = term._workspace_session_by_name(monorepo, 'demo')['retired']
    term._upsert_workspace_session(monorepo, 'demo', {'name': 'retired', 'task_terminal_retired_at': time.time()})
    assert client.post('/api/term/sessions', json={**body, 'restore': True}).status_code == 409
    assert client.delete('/api/term/sessions/' + created.json()['name']).status_code == 200
    assert client.post('/api/term/sessions', json={**body, 'restore': True}).status_code == 409
    reopened = client.post('/api/term/sessions', json=body)
    assert reopened.status_code == 200, reopened.text
    after = term._workspace_session_by_name(monorepo, 'demo')['retired']
    assert after['session_id'] == saved['session_id'] and not after.get('task_terminal_retired_at')


@pytest.mark.parametrize('delay', [None, 0, 2.5, 300])
def test_launch_delay_defaults_persists_and_only_waits_between_new_steps(
    client, seed_workspace, isolated_prefix, launch_waits, monkeypatch, delay,
):
    from core.routes import term
    folder = seed_workspace()
    steps = [{'label': str(i), 'command': 'printf ready'} for i in range(3)]
    if delay is None:
        # Older recipes acquire the default on read without rewriting their file.
        path = folder / '.lab/terminal-automations.json'
        path.parent.mkdir(exist_ok=True)
        raw = json.dumps({'automations': [{'id': 'dev', 'name': 'Development', 'steps': steps}]})
        path.write_text(raw)
        catalog = client.get('/api/term/automations?workspace_id=demo').json()
        assert path.read_text() == raw
    else:
        catalog = _save(client, 'demo', steps, launch_delay_seconds=delay)
        assert client.get('/api/term/automations?workspace_id=demo').json() == catalog
    expected = 5 if delay is None else delay
    assert catalog['automations'][0]['launch_delay_seconds'] == expected
    schema = client.get('/api/commands').json()['components']['schemas']['Automation']['properties']['launch_delay_seconds']
    assert schema['default'] == 5 and schema['minimum'] == 0 and schema['maximum'] == 300
    body = _launch(client, {'name': None}, catalog)
    preview = client.post('/api/term/automations/launch', json={**body, 'preview': True})
    assert preview.json()['launch_delay_seconds'] == expected
    assert launch_waits == []
    original = term.create_session
    seen = []
    def create(body, request):
        seen.append(list(launch_waits))
        return original(body, request)
    monkeypatch.setattr(term, 'create_session', create)
    result = client.post('/api/term/automations/launch', json=body).json()
    assert len(result['sessions']) == 3 and 'error' not in result
    assert seen == ([[], [expected], [expected, expected]] if expected else [[], [], []])
    assert launch_waits == ([expected, expected] if expected else [])
    launch_waits.clear()
    repeated = client.post('/api/term/automations/launch', json=body).json()
    assert all(row['already_running'] for row in repeated['sessions'])
    assert launch_waits == []


@pytest.mark.parametrize('delay', [-1, 301, None, 'invalid'])
def test_invalid_launch_delay_cannot_replace_saved_recipe(client, seed_workspace, isolated_prefix, delay):
    seed_workspace()
    catalog = _save(client, 'demo', [{'label': 'One', 'command': 'printf one'}])
    response = client.post('/api/term/automations', json={
        'workspace_id': 'demo', 'revision': catalog['revision'],
        'automations': [{**catalog['automations'][0], 'launch_delay_seconds': delay}],
    })
    assert response.status_code == 422
    assert client.get('/api/term/automations?workspace_id=demo').json() == catalog


def test_wait_keeps_settings_available_and_serializes_duplicate_run(
    client, seed_workspace, isolated_prefix, monkeypatch,
):
    seed_workspace()
    catalog = _save(client, 'demo', [{'label': 'One', 'command': 'printf one'},
                                     {'label': 'Two', 'command': 'printf two'}])
    body = _launch(client, {'name': None}, catalog)
    waiting, release, duplicate_started = threading.Event(), threading.Event(), threading.Event()
    def wait(seconds):
        assert seconds == 5
        waiting.set()
        assert release.wait(5)
    monkeypatch.setattr(terminal_automations, 'sleep', wait)
    def duplicate():
        duplicate_started.set()
        return client._inner.post('/api/term/automations/launch', json=body)
    with ThreadPoolExecutor(max_workers=3) as pool:
        first = pool.submit(client._inner.post, '/api/term/automations/launch', json=body)
        try:
            assert waiting.wait(5)
            again = pool.submit(duplicate)
            assert duplicate_started.wait(5)
            # Even a settings write can finish while this run is waiting.
            saved = pool.submit(client._inner.post, '/api/term/automations', json={
                'workspace_id': 'demo', 'revision': catalog['revision'],
                'automations': catalog['automations'],
            }).result(timeout=3)
            assert saved.status_code == 200
            assert not again.done()
        finally:
            release.set()
        original, repeated = first.result(timeout=5).json(), again.result(timeout=5).json()
    assert [row['name'] for row in original['sessions']] == [row['name'] for row in repeated['sessions']]
    assert all(row['already_running'] for row in repeated['sessions'])


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


def test_launch_preflights_every_path_uses_fixed_parent_folder_and_deduplicates(client, seed_workspace, monorepo, isolated_prefix):
    folder = seed_workspace()
    parent_folder = folder / "checkout with ' quotes"
    (parent_folder / 'frontend').mkdir(parents=True)
    parent = client.post('/api/term/sessions', json={
        'workspace_id': 'demo', 'kind': 'terminal', 'cwd': str(parent_folder), 'name': 'parent',
    }).json()
    steps = [{'label': 'Logs', 'command': "printf 'logs\\n'"},
             {'label': 'Frontend', 'command': 'npm run dev', 'cwd': 'frontend'}]
    catalog = _save(client, 'demo', steps)
    body = _launch(client, parent, catalog)
    preview = client.post('/api/term/automations/launch', json={**body, 'preview': True})
    assert preview.status_code == 200, preview.text
    assert [row['cwd'] for row in preview.json()['steps']] == [str(parent_folder), str(parent_folder / 'frontend')]
    assert len(client.get('/api/term/sessions?workspace_id=demo').json()) == 1
    result = client.post('/api/term/automations/launch', json=body)
    assert result.status_code == 200, result.text
    rows = result.json()['sessions']
    assert [row['label'] for row in rows] == ['Logs', 'Frontend']
    links = client.get('/api/objectives?workspace_id=demo').json()['terminal_links']
    assert links[rows[0]['session_id']]['task_id'] == body['task_id']
    from core.routes import term
    saved = term._workspace_session_by_name(monorepo, 'demo')
    assert saved[rows[0]['logical_name']]['parent_terminal'] == parent['logical_name']
    assert saved[rows[1]['logical_name']]['parent_terminal'] == rows[0]['logical_name']
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
    assert client.post('/api/term/automations/launch', json=_launch(client, parent, broken)).status_code == 400
    assert len(client.get('/api/term/sessions?workspace_id=demo').json()) == 3
    assert client.post('/api/term/automations/launch', json=_launch(client, parent, catalog)).status_code == 409


def test_launch_rejects_cross_workspace_parent_and_reports_partial_failure(client, seed_workspace, isolated_prefix, monkeypatch):
    seed_workspace()
    seed_workspace('other')
    parent = client.post('/api/term/sessions', json={'workspace_id': 'demo', 'kind': 'terminal'}).json()
    catalog = _save(client, 'demo', [{'label': 'One', 'command': 'printf one'}, {'label': 'Two', 'command': 'printf two'}])
    other = _save(client, 'other', [{'label': 'Other', 'command': 'printf other'}])
    assert client.post('/api/term/automations/launch', json=_launch(client, parent, other, workspace_id='other')).status_code == 404
    import core.routes.term as term
    original = term.create_session
    def fail_second(body, request):
        if body.label == 'Two':
            raise HTTPException(500, 'sample spawn failure')
        return original(body, request)
    monkeypatch.setattr(term, 'create_session', fail_second)
    result = client.post('/api/term/automations/launch', json=_launch(client, parent, catalog)).json()
    assert len(result['sessions']) == 1 and result['sessions'][0]['label'] == 'One'
    assert result['error'] == 'Two: sample spawn failure'
    assert len(client.get('/api/term/sessions?workspace_id=demo').json()) == 2


def test_direct_launch_creates_its_own_task_primary_in_definition_order(client, seed_workspace, isolated_prefix):
    folder = seed_workspace()
    def action(patch):
        response = client.post('/api/objectives', json={'workspace_id':'demo', 'action':patch})
        assert response.status_code == 200, response.text
        return response.json()
    objective = action({'type':'create', 'name':'Build'})['objectives'][0]
    oid = objective['id']
    task = action({'type':'task', 'objective_id':oid, 'title':'Develop'})['objectives'][0]['tasks'][0]
    action({'type':'task-update', 'objective_id':oid, 'task_id':task['id'], 'status':'in_progress'})
    cwd = folder / 'objectives' / oid
    (cwd / 'frontend').mkdir()
    catalog = _save(client, 'demo', [
        {'label':'First defined', 'cwd':'frontend', 'command':'printf first'},
        {'label':'Second defined', 'command':'printf second'},
    ])
    body = {'workspace_id':'demo', 'objective_id':oid, 'task_id':task['id'],
            'automation_id':'dev', 'revision':catalog['revision'], 'run_id':str(uuid.uuid4())}
    preview = client.post('/api/term/automations/launch', json={**body, 'preview':True})
    assert preview.status_code == 200, preview.text
    assert [row['cwd'] for row in preview.json()['steps']] == [str(cwd / 'frontend'), str(cwd)]
    assert client.get('/api/term/sessions?workspace_id=demo').json() == []
    result = client.post('/api/term/automations/launch', json=body)
    assert result.status_code == 200, result.text
    rows = result.json()['sessions']
    assert [row['label'] for row in rows] == ['First defined', 'Second defined']
    assert len(client.get('/api/term/sessions?workspace_id=demo').json()) == 2
    links = client.get('/api/objectives?workspace_id=demo').json()['terminal_links']
    assert links[rows[0]['session_id']]['task_id'] == task['id']
    assert links[rows[1]['session_id']]['view'] == 'tasks'
    assert not links[rows[1]['session_id']].get('task_id')
    repeated = client.post('/api/term/automations/launch', json=body).json()['sessions']
    assert [row['session_id'] for row in repeated] == [row['session_id'] for row in rows]
    assert all(row['already_running'] for row in repeated)
    # Another explicit run promotes its first step without killing the old run.
    replacement = client.post('/api/term/automations/launch', json={**body, 'run_id':str(uuid.uuid4())}).json()['sessions']
    links = client.get('/api/objectives?workspace_id=demo').json()['terminal_links']
    assert links[replacement[0]['session_id']]['task_id'] == task['id']
    assert links[rows[0]['session_id']]['task_id'] == task['id']
    assert links[rows[0]['session_id']]['primary'] is False
    assert len(client.get('/api/term/sessions?workspace_id=demo').json()) == 4


@pytest.mark.parametrize('parented', [False, True])
def test_launch_requires_wip_task_and_rechecks_status_after_preview(client, seed_workspace, isolated_prefix, parented):
    seed_workspace()
    parent = client.post('/api/term/sessions', json={'workspace_id':'demo', 'kind':'terminal'}).json() if parented else {'name': None}
    catalog = _save(client, 'demo', [{'label':'First', 'command':'printf ready'}])
    body = _launch(client, parent, catalog)
    before = client.get('/api/term/sessions?workspace_id=demo').json()
    for fields in [{'task_id':None}, {'objective_id':None}]:
        response = client.post('/api/term/automations/launch', json={**body, **fields})
        assert response.status_code == 422
    assert client.post('/api/term/automations/launch', json={**body, 'preview':True}).status_code == 200
    for status in ['paused', 'todo', 'done', 'wont_do']:
        changed = client.post('/api/objectives', json={'workspace_id':'demo', 'action':{
            'type':'task-update', 'objective_id':body['objective_id'], 'task_id':body['task_id'], 'status':status}})
        assert changed.status_code == 200, changed.text
        response = client.post('/api/term/automations/launch', json=body)
        assert response.status_code == 409 and 'In progress task' in response.text
        assert client.get('/api/term/sessions?workspace_id=demo').json() == before


def test_direct_launch_preflights_context_and_preserves_primary_on_partial_failure(client, seed_workspace, isolated_prefix, monkeypatch):
    seed_workspace()
    objective = client.post('/api/objectives', json={'workspace_id':'demo', 'action':{'type':'create','name':'Build'}}).json()['objectives'][0]
    oid = objective['id']
    task = client.post('/api/objectives', json={'workspace_id':'demo', 'action':{'type':'task','objective_id':oid,'title':'Develop'}}).json()['objectives'][0]['tasks'][0]
    client.post('/api/objectives', json={'workspace_id':'demo', 'action':{'type':'task-update','objective_id':oid,'task_id':task['id'],'status':'in_progress'}})
    catalog = _save(client, 'demo', [{'label':'First', 'command':'printf first'}, {'label':'Second', 'command':'printf second'}])
    body = {'workspace_id':'demo', 'objective_id':oid, 'task_id':task['id'], 'automation_id':'dev',
            'revision':catalog['revision'], 'run_id':str(uuid.uuid4())}
    for patch, status in [({'objective_id':None},422), ({'objective_id':'missing'},404),
                          ({'task_id':'missing'},404), ({'cwd':'/missing-automation-folder'},400),
                          ({'parent':'unrelated'},404), ({'revision':'stale'},409)]:
        response = client.post('/api/term/automations/launch', json={**body, **patch})
        assert response.status_code == status, response.text
        assert client.get('/api/term/sessions?workspace_id=demo').json() == []
    from core.routes import term
    original = term.create_session
    def fail_second(body, request):
        if body.label == 'Second':
            raise HTTPException(500, 'sample spawn failure')
        return original(body, request)
    monkeypatch.setattr(term, 'create_session', fail_second)
    result = client.post('/api/term/automations/launch', json=body).json()
    assert len(result['sessions']) == 1 and result['error'] == 'Second: sample spawn failure'
    links = client.get('/api/objectives?workspace_id=demo').json()['terminal_links']
    assert links[result['sessions'][0]['session_id']]['task_id'] == task['id']


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
    rows = client.post('/api/term/automations/launch', json=_launch(client, parent, catalog)).json()['sessions']
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
    child = client.post('/api/term/automations/launch', json=_launch(client, parent, catalog)).json()['sessions'][0]
    association = {'view':'workflow'} if owner == 'workflow' else {'objective_id':oid, 'view':'tasks'}
    after = action({'type':'terminal', 'session_id':child['session_id'], **association})
    assert after['terminal_links'][parent['session_id']] == before['terminal_links'][parent['session_id']]
    assert {key:value for key,value in after['terminal_links'][child['session_id']].items() if value is not None} == association
    assert 'main' not in after['terminal_links'][child['session_id']]
    assert 'task_id' not in after['terminal_links'][child['session_id']]


@pytest.mark.parametrize('with_parent', [False, True])
def test_native_launch_runs_once_in_tmux_and_keeps_exited_logs(native_creation_tmux, native_creation_client, seed_workspace, monkeypatch, with_parent):
    run, socket, _ = native_creation_tmux
    monkeypatch.setenv('SHELL', '/bin/sh')
    # The shared creation fixture originally sets a sleeping fake default shell.
    run('set-option', '-g', 'default-shell', '/bin/sh')
    client = native_creation_client
    folder = seed_workspace()
    (folder / 'frontend').mkdir()
    parent = client.post('/api/term/sessions', json={'workspace_id': 'demo', 'kind': 'terminal'}).json() if with_parent else None
    catalog = _save(client, 'demo', [
        {'label': 'Build', 'command': "printf 'build log\\n'; printf x >> count; exit 4"},
        {'label': 'Frontend', 'cwd': 'frontend', 'command': "printf 'frontend log\\n'; pwd"},
    ])
    body = _launch(client, parent or {'name':None}, catalog, **({} if parent else {'cwd':str(folder)}))
    # Exercise the actual server wait with real tmux launches, then ensure an
    # idempotent replay below never waits or re-executes the first command.
    waits = []
    def wait(seconds):
        started = time.monotonic()
        time.sleep(seconds)
        waits.append(time.monotonic() - started)
    monkeypatch.setattr(terminal_automations, 'sleep', wait)
    response = client.post('/api/term/automations/launch', json=body)
    assert response.status_code == 200, response.text
    rows = response.json()['sessions']
    assert len(rows) == 2 and all(row['tmux_socket'] == socket for row in rows)
    assert len(waits) == 1 and waits[0] >= 5
    assert len(client.get('/api/term/sessions?workspace_id=demo').json()) == 2 + int(with_parent)
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
    assert len(waits) == 1
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
