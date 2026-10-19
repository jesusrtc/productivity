"""References and ownership transfers preserve content, identities and processes."""
from pathlib import Path

import pytest
from fastapi import HTTPException
from lab import assistant_records as records, workspace_identity, storage
from core.routes.term import _enrich_session_details as enrich_session_details

from .test_assistant_document_tasks import legacy_tasks, owned_tasks  # noqa: F401
from .test_agent_activity import copilot_cli_events, write_events


@pytest.fixture()
def linked_workspace(monorepo, owned_tasks, seed_workspace, monkeypatch):
    from core.routes import term
    root, note, *_ = owned_tasks
    term._save_workspace(monorepo, 'demo', {'id':'demo', 'name':'demo'})
    seed_workspace('other')
    monkeypatch.delenv('LAB_TMUX_PREFIX', raising=False)
    vaults = [{'id':'client','path':monorepo},{'id':'__assistant__','path':root}]
    monkeypatch.setattr(term, '_known_vaults', lambda _:vaults)
    monkeypatch.setattr(term.lab_paths, 'find_framework_root', lambda:monorepo)
    monkeypatch.setattr(term, '_vault_root_for', lambda active, vault:root if vault == '__assistant__' else monorepo)
    monkeypatch.setattr(term, '_vault_id_for_root', lambda active, path:'__assistant__' if path == root else 'client')
    live = []
    monkeypatch.setattr(term, '_tmux_list', lambda *a, **kw:live)
    monkeypatch.setattr(term, '_enrich_session_details', lambda rows:None)
    monkeypatch.setattr(term, '_enrich_agent_session_names', lambda rows:None)
    def forbidden(*a, **kw):
        raise AssertionError('Document linking must never start/stop a process or send input')
    monkeypatch.setattr(term, '_tmux_command', forbidden)
    def session(where=root, workspace='__assistant__', logical='claude', legacy=False, agent='claude', cwd=None):
        entry = {'name':logical, 'kind':'claude', 'agent':agent, 'agent_session_id':'kept-conversation',
                 'cwd':str(cwd or root), 'label':'My agent', 'linked_scope':{'root':str(cwd or root)},
                 'linked_file':{'root':str(root), 'path':'source.md'}}
        term._upsert_workspace_session(where, workspace, entry)
        saved = term._get_workspace_sessions(where, workspace)[-1]
        name = 'lab-' + workspace + '-' + logical if legacy else term._tmux_name_for(workspace, logical, where)
        meta = term._load_meta(where)
        meta[name] = {**saved, 'workspace_id':workspace, 'logical_name':logical, 'created_at':123,
                      'tmux_socket':'kept-socket', 'pane_tty':'/dev/ttys999'}
        term._save_meta(where, meta)
        live.append({'name':name, 'tmux_socket':'kept-socket', 'created':123})
        return name
    return root, note, live, session


def link_document(client, root, note, workspace='demo'):
    result = client.post('/api/workspace-documents', json={'workspace_id':workspace, 'vault':'client',
                         'assistant_root':str(root), 'document_id':note.stem})
    assert result.status_code == 200, result.text


def link_terminal(client, note, workspace='__assistant__', vault='__assistant__', logical='claude'):
    result = client.patch('/api/term/sessions/metadata', json={'workspace_id':workspace, 'vault':vault,
                          'name':logical, 'linked_task':{'document_id':note.stem}})
    assert result.status_code == 200, result.text
    return result.json()['session']['linked_task']


def unlink_body(note, link, destination='workspace', source='__assistant__', vault='__assistant__', name='claude'):
    return {'workspace_id':'demo','vault':'client','source_workspace_id':source,'source_vault':vault,
            'name':name,'linked_task':link,'destination':destination}


def test_reference_deduplicates_resolves_titles_and_shared_sessions(client, linked_workspace, monorepo):
    from core.routes import term
    root, note, live, session = linked_workspace
    original = note.read_bytes()
    name = session()
    link_terminal(client, note)
    for workspace in ('demo','demo','other'):
        link_document(client, root, note, workspace)
    assert note.read_bytes() == original
    result = client.get('/api/workspace-documents?workspace_id=demo&vault=client').json()
    assert len(result) == 1 and result[0]['title'] == 'Task document'
    records.update(root, str(note.relative_to(root)), 'title', 'Renamed document')
    assert client.get('/api/workspace-documents?workspace_id=demo&vault=client').json()[0]['title'] == 'Renamed document'
    rows = client.get('/api/term/sessions?workspace_id=demo&vault=client').json()
    assert len(rows) == 1 and rows[0]['name'] == name
    assert rows[0]['document_source'] == {'workspace_id':'__assistant__','vault':'__assistant__','logical_name':'claude'}
    assert rows[0]['agent_session_id'] == 'kept-conversation' and rows[0]['cwd'] == str(root)
    assert term._get_workspace_sessions(monorepo, 'demo') == []
    assert not any(row.get('document_source') for row in client.get('/api/term/sessions').json())
    # Removing a workspace reference never unlinks/kills its source terminal.
    response = client.request('DELETE', '/api/workspace-documents', json={
        'workspace_id':'demo','vault':'client','assistant_root':str(root),'document_id':note.stem})
    assert response.status_code == 200
    assert client.get('/api/term/sessions?workspace_id=demo&vault=client').json() == []
    assert client.get('/api/term/sessions?workspace_id=other&vault=client').json()[0]['name'] == name
    assert live[0]['name'] == name


def test_checkout_document_references_keep_native_terminals_and_original_ownership(client, linked_workspace, monorepo):
    from core.routes import term
    root, note, live, session = linked_workspace
    original = session()
    link = link_terminal(client, note)
    before = term._get_workspace_sessions(root, '__assistant__')
    names = []
    for index, path in enumerate((monorepo/'project', monorepo/'trees/topic')):
        path.mkdir(parents=True)
        # A terminal's launch folder is fixed; each checkout gets its own tab.
        native = session(monorepo, 'demo', logical='checkout-'+str(index), cwd=path)
        names.append(native)
        response = client.patch('/api/term/sessions/metadata', json={'workspace_id':'demo','vault':'client',
            'name':'checkout-'+str(index),'linked_scope':{'base_root':str(monorepo/'workspaces/demo'),
                'project_root':str(path),'root':str(path)}})
        assert response.status_code == 200, response.text
        data = client.get('/api/scope-links',params={'path':str(path)}).json()
        response = client.put('/api/scope-links',json={'path':str(path),'expected':data['revision'],
            'links':[{'type':'internal-docs','assistant_root':str(root),'document_id':note.stem}]})
        assert response.status_code == 200, response.text
        rows = client.get('/api/term/sessions?workspace_id=demo&vault=client').json()
        assert [row['name'] for row in rows] == names
        assert not rows[-1].get('document_source') and not rows[-1].get('linked_task')
        assert rows[-1]['linked_scope']['root'] == str(path)
        assert rows[-1]['agent_session_id'] == 'kept-conversation'
        assert client.get('/api/workspace-documents?workspace_id=demo&vault=client').json() == []
        assert term._get_workspace_sessions(root,'__assistant__') == before
    original_link = next(row for row in client.get('/api/term/task-terminals?document_id='+note.stem).json() if row['name'] == original)
    assert original_link['linked_task'] == link
    assert [row['name'] for row in live] == [original,*names]


@pytest.mark.parametrize('label', [None, 'Planning conversation'])
def test_shared_terminal_keeps_its_name_and_independent_code_scope(client, linked_workspace, monorepo, label):
    from core.routes import term
    root, note, live, session = linked_workspace
    folder = monorepo/'trees/feature'; folder.mkdir(parents=True)
    name = session(cwd=folder)
    link_document(client, root, note)
    link = link_terminal(client, note)
    metadata = {'workspace_id':'__assistant__', 'vault':'__assistant__', 'name':'claude'}
    assert client.patch('/api/term/sessions/metadata', json={**metadata, 'label':label}).status_code == 200

    def shared():
        return client.get('/api/term/sessions?workspace_id=demo&vault=client').json()[0]

    # An absent custom label must remain absent so both surfaces derive the
    # same document title, rather than showing the internal name in a workspace.
    assert shared()['label'] == label
    assert shared()['linked_task'] == link
    code_scope = {'base_root':str(monorepo / 'workspaces/demo'), 'project_root':str(monorepo / 'repo'),
                  'root':str(monorepo / 'trees/feature'), 'worktree':str(monorepo / 'trees/feature'),
                  'label':'Code · feature', 'config_scope':'client::demo'}
    source = shared()['document_source']
    metadata = {'workspace_id':source['workspace_id'], 'vault':source['vault'], 'name':source['logical_name']}
    original = term._get_workspace_sessions(root, '__assistant__')[0]
    response = client.patch('/api/term/sessions/metadata', json={**metadata, 'linked_scope':code_scope})
    assert response.status_code == 200, response.text
    row = shared()
    assert row['linked_scope']['root'] == code_scope['root']
    for field in ('linked_task', 'linked_file', 'label', 'cwd', 'agent_session_id'):
        assert row.get(field) == original.get(field)
    assert row['name'] == name and row['document_source'] == source
    assert term._get_workspace_sessions(monorepo, 'demo') == []

    # Clearing a fixed launch folder is rejected without changing the document,
    # conversation, or the independent display metadata of that folder.
    assert client.patch('/api/term/sessions/metadata', json={**metadata, 'linked_scope':None}).status_code == 409
    assert shared()['linked_task'] == link and shared()['linked_scope'] == row['linked_scope']
    assert live[0]['name'] == name


@pytest.mark.parametrize('legacy', [False, True])
def test_keep_in_workspace_preserves_identity_and_cannot_be_readopted(client, linked_workspace, monorepo, legacy):
    from core.routes import term
    root, note, live, session = linked_workspace
    name = session(legacy=legacy)
    session(monorepo, 'demo')  # Force a logical-name collision.
    link_document(client, root, note)
    link = link_terminal(client, note)
    original = term._get_workspace_sessions(root, '__assistant__')[0]
    response = client.post('/api/workspace-documents/unlink-terminal', json=unlink_body(note, link))
    assert response.status_code == 200, response.text
    moved = response.json()['session']
    assert moved['name'] != 'claude' and moved['session_id'] == original['session_id']
    for field in ('cwd','agent_session_id','label','linked_file','linked_scope'):
        assert moved[field] == original[field]
    assert 'linked_task' not in moved
    assert term._get_workspace_sessions(root, '__assistant__') == []
    assert name not in term._sync_meta(root, live)
    assert term._sync_meta(monorepo, live)[name]['logical_name'] == moved['name']
    assert term._resolve_session_vault_root(name, monorepo) == monorepo
    # Recovery after losing runtime metadata keeps the new owner, even for old names.
    term._save_meta(monorepo, {})
    recovered = term._sync_meta(monorepo, live)[name]
    assert recovered['workspace_id'] == 'demo' and recovered['agent_session_id'] == 'kept-conversation'
    assert recovered['tmux_socket'] == 'kept-socket'
    assert workspace_identity.session_owner(monorepo, name) == ('demo', moved['name'])


@pytest.mark.parametrize('destination', ['workspace', 'assistant'])
@pytest.mark.parametrize('agent', ['codex', 'claude', 'copilot'])
def test_native_terminal_unlink_destination_and_stopped_link(client, linked_workspace, monorepo, destination, agent):
    from core.routes import term
    root, note, live, session = linked_workspace
    name = session(monorepo, 'demo', agent=agent)
    link = link_terminal(client, note, 'demo', 'client')
    live.clear()  # A stopped tab can also be reassigned; no implicit restart.
    response = client.post('/api/workspace-documents/unlink-terminal', json=unlink_body(
        note, link, destination, 'demo', 'client'))
    assert response.status_code == 200, response.text
    owner_root, owner_id = (monorepo, 'demo') if destination == 'workspace' else (root, '__assistant__')
    saved = term._get_workspace_sessions(owner_root, owner_id)
    assert len(saved) == 1 and saved[0]['agent_session_id'] == 'kept-conversation'
    assert saved[0]['agent'] == agent
    assert 'linked_task' not in saved[0]
    assert workspace_identity.session_owner(owner_root, name) == (owner_id, saved[0]['name'])


def test_invalid_or_stale_links_and_forbidden_transfers_write_nothing(client, linked_workspace, monorepo, monkeypatch):
    from core.routes import term
    root, note, live, session = linked_workspace
    session()
    link_document(client, root, note)
    link = link_terminal(client, note)
    before = term._load_workspace(root, '__assistant__')
    body = unlink_body(note, {**link, 'task_id':'changed'})
    assert client.post('/api/workspace-documents/unlink-terminal', json=body).status_code == 409
    assert client.post('/api/workspace-documents', json={'workspace_id':'demo','vault':'client',
        'assistant_root':str(root),'document_id':'../outside'}).status_code == 400
    assert client.post('/api/workspace-documents', json={'workspace_id':'../../outside','vault':'client',
        'assistant_root':str(root),'document_id':note.stem}).status_code == 400
    access = term._require_workspace_access
    def forbid(request, active, target, workspace):
        if target == root:
            raise HTTPException(403, 'forbidden')
        return access(request, active, target, workspace)
    monkeypatch.setattr(term, '_require_workspace_access', forbid)
    assert client.post('/api/workspace-documents/unlink-terminal', json=unlink_body(note, link)).status_code == 403
    assert term._load_workspace(root, '__assistant__') == before
    assert term._get_workspace_sessions(monorepo, 'demo') == []


def test_transfer_rolls_back_metadata_runtime_and_indexes(client, linked_workspace, monorepo, monkeypatch):
    from core.routes import term
    root, note, live, session = linked_workspace
    session()
    link_document(client, root, note)
    link = link_terminal(client, note)
    files = [term._workspace_json(root, '__assistant__'), term._workspace_json(monorepo, 'demo'),
             term._sessions_file(root)]
    before = {file:file.read_bytes() for file in files}
    original = storage.write_json
    def fail(file, value):
        if file == term._workspace_json(monorepo, 'demo'):
            raise OSError('disk unavailable')
        return original(file, value)
    monkeypatch.setattr(storage, 'write_json', fail)
    with pytest.raises(OSError, match='disk unavailable'):
        client.post('/api/workspace-documents/unlink-terminal', json=unlink_body(note, link))
    assert before == {file:file.read_bytes() for file in files}
    assert term._get_workspace_sessions(monorepo, 'demo') == []


def test_attention_includes_inactive_and_shared_workspaces_without_summaries(client, linked_workspace, monkeypatch):
    from core import agent_activity
    root, note, live, session = linked_workspace
    name = session()
    link_terminal(client, note)
    link_document(client, root, note)
    live[0]['terminal_status'] = {'version':1,'state':'attention','message':'Please review','revision':1,'id':'event'}
    monkeypatch.setattr(agent_activity, 'enrich', lambda rows: pytest.fail('indicators must not scan transcripts'))
    data = client.get('/api/workspace-documents/attention').json()
    assert data['client::demo'][0]['name'] == name
    assert data['__assistant__::__assistant__'][0]['terminal_status'] == live[0]['terminal_status']
    assert data['client::demo'][0]['terminal_status'] == live[0]['terminal_status']
    assert data['client::demo'][0]['workspace_id'] == '__assistant__'
    assert data['client::demo'][0]['vault'] == '__assistant__'
    assert data['client::demo'][0]['logical_name'] == 'claude'
    assert 'cwd' not in data['client::demo'][0]


def test_attention_includes_framework_home_outside_registered_vaults(client, linked_workspace, tmp_path, monkeypatch):
    from core.routes import term
    _, _, live, session = linked_workspace
    framework = tmp_path / 'framework'
    framework.mkdir()
    monkeypatch.setattr(term.lab_paths, 'find_framework_root', lambda:framework)
    original = session(where=framework, workspace='__self__', logical='home-agent')
    # Legacy names cannot be rediscovered from Home's shared saved UUIDs in a
    # different vault; only their original runtime registry owns them.
    name = term._legacy_current_tmux_name_for('__self__', 'home-agent', framework)
    metadata = term._load_meta(framework)
    metadata[name] = metadata.pop(original)
    term._save_meta(framework, metadata)
    live[0]['name'] = name
    live[0]['terminal_status'] = {'version':1, 'state':'attention', 'message':'Choose next step', 'revision':1, 'id':'home-report'}
    monkeypatch.setattr(term, '_enrich_session_details', lambda rows:pytest.fail('header must not read transcripts'))
    result = client.get('/api/workspace-documents/attention').json()
    row, = result['framework::__self__']
    assert row['name'] == name and row['workspace_id'] == '__self__'
    assert row['terminal_status']['id'] == 'home-report'
    monkeypatch.setattr(term.auth, 'is_admin', lambda user:False)
    assert 'framework::__self__' not in client.get('/api/workspace-documents/attention').json()


@pytest.mark.parametrize('recording,boundary,expected', [
    ('tool-response', 'user.message', 'working'),
    ('tool-response', 'tool.execution_start', 'working'),
    ('tool-response', 'assistant.turn_end', 'working'),
    ('tool-response', 'session.shutdown', 'completed'),
    ('abrupt-resume', 'session.resume', 'interrupted'),
])
def test_native_copilot_activity_reaches_terminal_and_shared_workspace_apis(
        client, linked_workspace, tmp_path, monkeypatch, recording, boundary, expected):
    from core.routes import term
    # Linking fixtures normally omit all agent details. Restore the real
    # activity path here, while keeping terminal capture out of this check.
    monkeypatch.setattr(term, '_enrich_session_details', enrich_session_details)
    monkeypatch.setattr(term, '_infer_session_summary', lambda *args: None)
    root, note, _, session = linked_workspace
    name = session(agent='copilot')
    link_terminal(client, note)
    for workspace in ('demo', 'other'):
        link_document(client, root, note, workspace)
    home = tmp_path / 'copilot'
    monkeypatch.setenv('COPILOT_HOME', str(home))
    events = copilot_cli_events(recording)
    index = next(i for i, event in enumerate(events) if event['type'] == boundary)
    write_events(home / 'session-state/kept-conversation/events.jsonl', events[:index + 1])
    row = client.get('/api/term/sessions', params={'workspace_id':'demo','vault':'client'}).json()[0]
    assert row['name'] == name and row['agent'] == 'copilot'
    assert row['agent_session_id'] == 'kept-conversation'
    assert row['agent_activity']['state'] == expected
    attention = client.get('/api/workspace-documents/attention').json()
    for scope in ('client::demo', 'client::other', '__assistant__::__assistant__'):
        assert attention[scope][0]['name'] == name
        assert 'agent_activity' not in attention[scope][0], 'provider state must not drive indicators'


@pytest.mark.parametrize('agent', ['codex', 'claude', 'copilot'])
def test_assistant_documents_derive_from_saved_links_without_tmux(client, linked_workspace, monkeypatch, agent):
    from core.routes import term
    root, note, live, session = linked_workspace
    session(agent=agent)
    link = link_terminal(client, note)
    # Multiple task links in one document appear once, using the document title.
    term._upsert_workspace_session(root, '__assistant__', {'name':'second', 'kind':agent,
        'linked_task':{**link, 'task_id':'task', 'title':'Task title'}})
    live.clear()
    def no_tmux(*args, **kwargs):
        raise AssertionError('Listing linked documents must not inspect or start processes')
    monkeypatch.setattr(term, '_tmux_list', no_tmux)
    response = client.get('/api/workspace-documents?workspace_id=__assistant__&vault=__assistant__')
    assert response.status_code == 200, response.text
    assert len(response.json()) == 1
    assert response.json()[0]['title'] == 'Task document'
    assert response.json()[0]['task_id'] is None
    records.update(root, str(note.relative_to(root)), 'title', 'New document title')
    assert client.get('/api/workspace-documents?workspace_id=__assistant__').json()[0]['title'] == 'New document title'
    term._upsert_workspace_session(root, '__assistant__', {'name':'claude', 'linked_task':None})
    term._upsert_workspace_session(root, '__assistant__', {'name':'second', 'linked_task':None})
    assert client.get('/api/workspace-documents?workspace_id=__assistant__').json() == []


def test_notification_context_uses_native_objective_and_inherited_parent_in_one_batch(
        client, linked_workspace, monorepo, monkeypatch):
    from core.routes import term
    from core.routes import workspace_documents as route
    from core import task_terminal_cleanup
    from lab import objectives, objective_store

    root, note, live, session = linked_workspace
    parent = session(monorepo, 'demo', 'parent')
    child = session(monorepo, 'demo', 'child')
    saved = {row['name']: row for row in term._get_workspace_sessions(monorepo, 'demo')}
    first = objectives.mutate(monorepo, 'demo', {'type':'create', 'name':'Owner Objective'})['objectives'][0]['id']
    second_data = objectives.mutate(monorepo, 'demo', {'type':'create', 'name':'Other Objective'})
    second = next(row['id'] for row in second_data['objectives'] if row['id'] != first)
    objectives.mutate(monorepo, 'demo', {'type':'terminal', 'objective_id':first,
                                       'session_id':saved['parent']['session_id']})
    task_terminal_cleanup.save_parents(monorepo, 'demo', {'child':'parent'})
    link_terminal(client, note, workspace='demo', vault='client', logical='child')
    link_document(client, root, note, workspace='other')
    for row in live:
        row['terminal_status'] = {'version':1, 'state':'attention', 'message':'Review', 'id':row['name'], 'revision':1}
    reads = []
    read = objective_store.read
    load = objectives.load
    payload = objectives.payload
    monkeypatch.setattr(objective_store, 'read', lambda folder:(reads.append(folder), read(folder))[1])
    monkeypatch.setattr(objectives, 'payload', lambda *a:pytest.fail('Notification names must not load document bodies'))
    monkeypatch.setattr(objectives, 'load', lambda *a, **kw:pytest.fail('Notification names must not refresh checklists'))
    before = {file:file.read_bytes() for file in monorepo.rglob('*.json')}
    result = client.get('/api/workspace-documents/attention')
    assert result.status_code == 200, result.text
    rows = {row['name']: row for row in result.json()['client::demo']}
    assert rows[parent]['notification_context'] == {'workspace':'demo', 'objective':'Owner Objective'}
    assert rows[child]['notification_context'] == rows[parent]['notification_context']
    borrowed = result.json()['client::other'][0]
    assert borrowed['name'] == child and borrowed['notification_context'] == rows[child]['notification_context']
    assert borrowed['workspace_id'] == 'demo', 'Borrowing must not relabel a terminal with the destination Objective'
    assert len(reads) == 1, 'Read owner metadata once, not per terminal or shared view'
    assert all(file.read_bytes() == content for file, content in before.items()), 'Reading labels must not change managed metadata'
    # An explicit child Objective takes precedence over its inherited parent.
    monkeypatch.setattr(objectives, 'load', load)
    monkeypatch.setattr(objectives, 'payload', payload)
    objectives.mutate(monorepo, 'demo', {'type':'terminal', 'objective_id':second,
                                       'session_id':saved['child']['session_id']})
    contexts = route._notification_context(monorepo, 'demo', [rows[parent], rows[child]])
    assert contexts[child]['objective'] == 'Other Objective'
    assert contexts[parent]['objective'] == 'Owner Objective'


def test_invalid_notification_context_does_not_hide_alerts(client, linked_workspace, monorepo, monkeypatch):
    from core.routes import workspace_documents as route
    _, _, live, session = linked_workspace
    name = session(monorepo, 'demo', 'notify')
    live[0]['terminal_status'] = {'version':1, 'state':'attention', 'message':'Keep this alert', 'id':'active', 'revision':1}
    def unavailable(*args):
        raise ValueError('Unavailable Objective metadata')
    monkeypatch.setattr(route, '_notification_context', unavailable)
    response = client.get('/api/workspace-documents/attention')
    assert response.status_code == 200
    row, = response.json()['client::demo']
    assert row['name'] == name and row['terminal_status']['id'] == 'active'
    assert 'notification_context' not in row
