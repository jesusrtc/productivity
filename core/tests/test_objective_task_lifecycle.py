"""Task branches move intact and destructive deletion respects ownership."""
from pathlib import Path
from types import SimpleNamespace

import pytest
from lab import assistant_documents, objectives


@pytest.fixture()
def branch(monorepo, seed_workspace):
    folder = seed_workspace()
    data = objectives.mutate(monorepo, 'demo', {'type':'create', 'name':'Branch project'})
    oid = data['objectives'][0]['id']
    def apply(operation, **fields):
        return objectives.mutate(monorepo, 'demo', {'type':operation, 'objective_id':oid, **fields})
    def task(title, parent=None):
        data = apply('task', title=title, parent_id=parent)
        return next(t for t in objectives._tasks(data['objectives'][0]) if t['title'] == title)
    parent = task('Parent')
    child = task('Child', parent['id'])
    grandchild = task('Grandchild', child['id'])
    sibling = task('Sibling')
    return SimpleNamespace(folder=folder, oid=oid, apply=apply, task=task,
                           parent=parent, child=child, grandchild=grandchild, sibling=sibling)


def review(monorepo, branch, task=None, **fields):
    action = {'type':'task-delete', 'objective_id':branch.oid, 'task_id':(task or branch.parent)['id'], **fields}
    preview = objectives.task_delete_preview(monorepo, 'demo', action)
    return preview, {**action, 'confirmed':True, 'confirm_title':preview['title'], 'review_token':preview['review_token']}


def test_moves_preserve_branch_identity_details_assets_and_terminal_links(monorepo, branch):
    branch.apply('terminal', session_id='child-session', task_id=branch.child['id'])
    branch.apply('terminal', session_id='grandchild-session', task_id=branch.grandchild['id'])
    data = branch.apply('resource', kind='link', title='Evidence', url='https://example.com')
    branch.apply('task-asset', task_id=branch.child['id'], resource_id=data['objectives'][0]['resources'][-1]['id'])
    before = objectives.payload(monorepo, 'demo')
    original = next(t for t in objectives._tasks(before['objectives'][0]) if t['id'] == branch.child['id'])
    data = branch.apply('task-move', task_id=branch.child['id'], parent_id=None, before_id=branch.parent['id'])
    o = data['objectives'][0]
    assert [t['id'] for t in o['tasks']] == [branch.child['id'], branch.parent['id'], branch.sibling['id']]
    moved = o['tasks'][0]
    assert moved['children'][0]['id'] == branch.grandchild['id']
    assert moved['document_id'] == original['document_id'] and moved['tab_id'] == original['tab_id']
    assert moved['assets'] == original['assets'] and data['terminal_links'] == before['terminal_links']
    resource = next(r for r in o['resources'] if r['id'] == moved['document_id'])
    tab = next(t for t in resource['content']['tabs'] if t['id'] == moved['tab_id'])
    assert tab['parent']['id'] == resource['id']
    data = branch.apply('task-move', task_id=moved['id'], parent_id=branch.sibling['id'])
    o = data['objectives'][0]
    assert o['tasks'][1]['children'][0]['id'] == moved['id']
    resource = next(r for r in o['resources'] if r['id'] == moved['document_id'])
    tab = next(t for t in resource['content']['tabs'] if t['id'] == moved['tab_id'])
    assert tab['parent']['id'] == branch.sibling['tab_id']
    assert [t['body'] for t in resource['content']['tabs']] == [t['body'] for t in before['objectives'][0]['resources'][0]['content']['tabs']]


@pytest.mark.parametrize('patch', [
    {'parent':'parent'}, {'parent':'grandchild'}, {'parent_id':'missing'}, {'before_id':'missing'},
])
def test_invalid_moves_leave_documents_and_registry_intact(monorepo, branch, patch):
    patch = dict(patch)
    if 'parent' in patch:
        patch['parent_id'] = getattr(branch, patch.pop('parent'))['id']
    before = objectives.payload(monorepo, 'demo')
    paths = {branch.folder/r['path']:(branch.folder/r['path']).read_bytes() for r in before['objectives'][0]['resources']}
    with pytest.raises(ValueError):
        branch.apply('task-move', task_id=branch.parent['id'], **patch)
    assert objectives.payload(monorepo, 'demo') == before
    assert all(p.read_bytes() == raw for p, raw in paths.items())


def test_move_rejects_conflicting_recurrence_before_document_write(monorepo, branch):
    recurrence = {'every':1, 'unit':'day', 'time':'09:00', 'timezone':'UTC', 'reactivate_before_minutes':1440}
    branch.apply('task-update', task_id=branch.parent['id'], due='2026-10-12', recurrence=recurrence)
    branch.apply('task-update', task_id=branch.sibling['id'], due='2026-10-12', recurrence=recurrence)
    before = objectives.payload(monorepo, 'demo')
    with pytest.raises(ValueError, match='Schedule the parent'):
        branch.apply('task-move', task_id=branch.parent['id'], parent_id=branch.sibling['id'])
    assert objectives.payload(monorepo, 'demo') == before


def test_delete_requires_review_both_confirmations_exact_name_and_current_files(monorepo, branch):
    preview, action = review(monorepo, branch)
    before = objectives.payload(monorepo, 'demo')
    for patch, expected in [({'confirmed':False},preview['revision']), ({'confirm_title':'parent'},preview['revision']),
                            ({'review_token':'incorrect'},preview['revision']), ({},None)]:
        with pytest.raises(ValueError):
            objectives.mutate(monorepo, 'demo', {**action, **patch}, expected)
        assert objectives.payload(monorepo, 'demo') == before
    doc = before['objectives'][0]['resources'][0]
    path = branch.folder/doc['path']
    owner, body, tabs = assistant_documents.unpack(path.read_bytes())
    path.write_bytes(assistant_documents.pack(owner, body+'\nNew content', tabs))
    with pytest.raises(ValueError, match='changed elsewhere'):
        objectives.mutate(monorepo, 'demo', action, preview['revision'])
    preview, action = review(monorepo, branch)
    branch.task('New sibling')
    with pytest.raises(ValueError, match='changed elsewhere'):
        objectives.mutate(monorepo, 'demo', action, preview['revision'])


def test_delete_branch_removes_exclusive_assets_and_preserves_shared_sources(monorepo, branch, tmp_path):
    resource_ids = {}
    for kind, title, extra in [('document','Exclusive doc',{'body':'Exclusive evidence'}),
                               ('notebook','Exclusive notebook',{}), ('document','Shared doc',{'body':'Shared evidence'}),
                               ('link','External link',{'url':'https://example.com'})]:
        data = branch.apply('resource', kind=kind, title=title, **extra)
        rid = data['objectives'][0]['resources'][-1]['id']
        resource_ids[title] = rid
        branch.apply('task-asset', task_id=branch.child['id'], resource_id=rid)
    branch.apply('task-asset', task_id=branch.sibling['id'], resource_id=resource_ids['Shared doc'])
    external = branch.folder/'source.py';external.write_text('preserve source')
    data = branch.apply('resource', kind='file', title='Source', path='source.py')
    branch.apply('task-asset', task_id=branch.parent['id'], resource_id=data['objectives'][0]['resources'][-1]['id'])
    tree = tmp_path/'checkout';tree.mkdir();(tree/'dirty.txt').write_text('uncommitted')
    branch.apply('worktree', path=str(tree), kind='folder')
    branch.apply('task-asset', task_id=branch.parent['id'], folder={'root':str(tree), 'path':'.'})
    before = objectives.payload(monorepo, 'demo')['objectives'][0]
    shared = next(r for r in before['resources'] if r['id'] == resource_ids['Shared doc'])
    shared_bytes = (branch.folder/shared['path']).read_bytes()
    preview, action = review(monorepo, branch)
    data = objectives.mutate(monorepo, 'demo', action, preview['revision'])
    o = data['objectives'][0]
    assert [t['id'] for t in o['tasks']] == [branch.sibling['id']]
    assert [r['title'] for r in o['resources']] == ['Tasks.md', 'Shared doc.md']
    detail_tabs = o['resources'][0]['content']['tabs']
    assert [t['id'] for t in detail_tabs] == [branch.sibling['tab_id']]
    for path in preview['files']:
        assert not (branch.folder/path).exists()
    assert (branch.folder/shared['path']).read_bytes() == shared_bytes
    assert external.read_text() == 'preserve source' and (tree/'dirty.txt').read_text() == 'uncommitted'
    assert not list(branch.folder.rglob('.task-delete-*'))


def test_failed_terminal_cleanup_restores_all_task_files(monorepo, branch):
    data = branch.apply('resource', kind='document', title='Only mine', body='Retain on failure')
    branch.apply('task-asset', task_id=branch.parent['id'], resource_id=data['objectives'][0]['resources'][-1]['id'])
    branch.apply('terminal', session_id='primary', task_id=branch.parent['id'])
    before = objectives.payload(monorepo, 'demo')
    files = {branch.folder/r['path']:(branch.folder/r['path']).read_bytes() for r in before['objectives'][0]['resources']}
    preview, action = review(monorepo, branch)
    with pytest.raises(ValueError, match='through Lab'):
        objectives.mutate(monorepo, 'demo', action, preview['revision'])
    def fail(plan):
        raise ValueError('terminal kill refused')
    with pytest.raises(ValueError, match='kill refused'):
        objectives.mutate(monorepo, 'demo', action, preview['revision'], delete_terminals=fail)
    assert objectives.payload(monorepo, 'demo') == before
    assert all(path.read_bytes() == raw for path, raw in files.items())
    assert not list(branch.folder.rglob('.task-delete-*'))


def test_partial_metadata_save_failure_restores_branch_content(monorepo, branch, monkeypatch):
    from lab import objective_store
    before = objectives.payload(monorepo,'demo')
    preview, action = review(monorepo, branch)
    save = objective_store.save
    writes = []
    def fail_once(folder, data):
        save(folder, data)
        writes.append(True)
        if len(writes) == 1:
            raise OSError('state write failed')
    monkeypatch.setattr(objective_store, 'save', fail_once)
    with pytest.raises(OSError, match='state write failed'):
        objectives.mutate(monorepo,'demo',action,preview['revision'])
    assert objectives.payload(monorepo,'demo') == before
    assert len(writes) == 2


def test_delete_api_purges_stopped_and_live_branch_terminals_keeps_other_owners(client, monorepo, branch, monkeypatch):
    from core.routes import term
    from core import terminal_requests
    sessions = {}
    for name in ['primary','child','extra','grand-extra','sibling','main']:
        term._upsert_workspace_session(monorepo, 'demo', {'name':name, 'kind':'terminal', 'cwd':str(branch.folder)})
        sessions[name] = next(r for r in term._get_workspace_sessions(monorepo, 'demo') if r['name'] == name)
    for name, task in [('primary',branch.parent), ('child',branch.child), ('sibling',branch.sibling)]:
        branch.apply('terminal', session_id=sessions[name]['session_id'], task_id=task['id'])
    for name in ['extra','grand-extra']:
        branch.apply('terminal', session_id=sessions[name]['session_id'], view='tasks')
    branch.apply('terminal', session_id=sessions['main']['session_id'], main='objective')
    graph = {sessions[c]['session_id']:sessions[p]['session_id'] for c, p in
             [('extra','child'), ('grand-extra','extra'), ('sibling','primary'), ('main','primary')]}
    monkeypatch.setattr(term, '_tmux_available', lambda:True)
    names = {name:term._tmux_name_for('demo', name, monorepo) for name in sessions}
    live = {names['primary'], names['extra']}
    monkeypatch.setattr(term, '_tmux_find_session_socket', lambda name: 'fixture' if name in live else None)
    killed = []
    def run(command, **kwargs):
        name = command[-1];killed.append(name);live.discard(name)
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(term.subprocess, 'run', run)
    forgotten = []
    monkeypatch.setattr(terminal_requests, 'forget', lambda names:forgotten.extend(names))
    action = {'objective_id':branch.oid, 'task_id':branch.parent['id'], 'terminal_parents':graph}
    preview = client.post('/api/objectives/task-delete-preview', json={'workspace_id':'demo', 'action':action}).json()
    expected_ids = {sessions[n]['session_id'] for n in ['primary','child','extra','grand-extra']}
    assert set(preview['terminal_ids']) == expected_ids
    response = client.post('/api/objectives', json={'workspace_id':'demo', 'expected':preview['revision'],
        'action':{**action, 'type':'task-delete', 'confirmed':True, 'confirm_title':preview['title'], 'review_token':preview['review_token']}})
    assert response.status_code == 200, response.text
    assert set(killed) == {names['primary'],names['extra']}
    assert {r['name'] for r in term._get_workspace_sessions(monorepo,'demo')} == {'sibling','main'}
    assert set(response.json()['terminal_links']) == {sessions[n]['session_id'] for n in ['sibling','main']}
    assert set(forgotten) == {names[n] for n in ['primary','child','extra','grand-extra']}


def test_busy_notebook_rejects_before_files_or_terminals_change(client, monorepo, branch, monkeypatch):
    from core import notebook_kernel
    from core.routes import objectives as route
    data = branch.apply('resource', kind='notebook', title='Running analysis')
    branch.apply('task-asset', task_id=branch.parent['id'], resource_id=data['objectives'][0]['resources'][-1]['id'])
    preview, action = review(monorepo, branch)
    before = objectives.payload(monorepo, 'demo')
    raw = {p:(branch.folder/p).read_bytes() for p in preview['files']}
    monkeypatch.setattr(notebook_kernel, 'workspace_busy', lambda *_:True)
    monkeypatch.setattr(route, '_delete_task_terminals', lambda *_:pytest.fail('terminals closed before notebook validation'))
    response = client.post('/api/objectives', json={'workspace_id':'demo', 'expected':preview['revision'], 'action':action})
    assert response.status_code == 400 and 'finish' in response.text
    assert objectives.payload(monorepo, 'demo') == before
    assert all((branch.folder/p).read_bytes() == value for p, value in raw.items())


def test_delete_preserves_pinned_tabs_and_unrelated_nested_document_content(monorepo, branch):
    data = branch.apply('subtab', resource_id=branch.parent['document_id'], title='Independent note', body='Keep this note', parent_id=branch.parent['tab_id'])
    resource = data['objectives'][0]['resources'][0]
    independent = resource['content']['tabs'][-1]
    branch.apply('asset-star', resource_id=branch.child['document_id'], tab_id=branch.child['tab_id'], starred=True)
    preview, action = review(monorepo, branch)
    data = objectives.mutate(monorepo, 'demo', action, preview['revision'])
    resource = data['objectives'][0]['resources'][0]
    tabs = {t['id']:t for t in resource['content']['tabs']}
    assert set(tabs) == {branch.child['tab_id'], branch.sibling['tab_id'], independent['id']}
    assert tabs[independent['id']]['body'] == 'Keep this note'
    assert tabs[branch.child['tab_id']]['parent']['id'] == resource['id']


def test_shared_file_alias_protects_owned_document_bytes(monorepo, branch):
    data = branch.apply('resource', kind='document', title='Aliased source', body='Preserve shared bytes')
    doc = data['objectives'][0]['resources'][-1]
    branch.apply('task-asset', task_id=branch.parent['id'], resource_id=doc['id'])
    branch.apply('resource', kind='file', title='Source alias', path=doc['path'])
    original = (branch.folder/doc['path']).read_bytes()
    preview, action = review(monorepo, branch)
    objectives.mutate(monorepo,'demo',action,preview['revision'])
    assert (branch.folder/doc['path']).read_bytes() == original


def test_native_tmux_move_keeps_pids_delete_kills_branch_and_retains_sibling(client, monorepo, branch, monkeypatch):
    import shutil
    import subprocess
    import uuid
    from core.routes import term
    binary = shutil.which('tmux')
    if not binary:
        pytest.skip('tmux required')
    socket = 'lab-task-delete-' + uuid.uuid4().hex[:12]
    monkeypatch.setattr(term, '_tmux_command', lambda _socket, *args:[binary, '-L', socket, *args])
    sessions = {}
    names = {}
    try:
        for name, task in [('primary',branch.parent), ('child',branch.child), ('sibling',branch.sibling)]:
            term._upsert_workspace_session(monorepo, 'demo', {'name':name, 'kind':'terminal', 'cwd':str(branch.folder)})
            sessions[name] = next(s for s in term._get_workspace_sessions(monorepo,'demo') if s['name'] == name)
            names[name] = term._tmux_name_for('demo', name, monorepo)
            subprocess.run([binary,'-L',socket,'new-session','-d','-s',names[name],'-c',str(branch.folder),'bash'], check=True)
            branch.apply('terminal', session_id=sessions[name]['session_id'], task_id=task['id'])
        def pid(name):
            return subprocess.check_output([binary,'-L',socket,'display-message','-p','-t',names[name],'#{pane_pid}'],text=True).strip()
        original = {name:pid(name) for name in names}
        branch.apply('task-move', task_id=branch.child['id'], parent_id=branch.sibling['id'])
        assert {name:pid(name) for name in names} == original
        preview, action = review(monorepo, branch)
        response = client.post('/api/objectives', json={'workspace_id':'demo', 'expected':preview['revision'], 'action':action})
        assert response.status_code == 200, response.text
        assert subprocess.run([binary,'-L',socket,'has-session','-t',names['primary']],capture_output=True).returncode != 0
        assert pid('child') == original['child'] and pid('sibling') == original['sibling']
        preview, action = review(monorepo, branch, branch.sibling)
        response = client.post('/api/objectives', json={'workspace_id':'demo', 'expected':preview['revision'], 'action':action})
        assert response.status_code == 200, response.text
        for name in ['child','sibling']:
            assert subprocess.run([binary,'-L',socket,'has-session','-t',names[name]],capture_output=True).returncode != 0
        assert not term._get_workspace_sessions(monorepo,'demo')
    finally:
        subprocess.run([binary,'-L',socket,'kill-server'],capture_output=True)
