"""References and ownership transfers preserve content, identities and processes."""
from pathlib import Path

import pytest
from fastapi import HTTPException
from lab import assistant_records as records, workspace_identity, storage

from .test_assistant_document_tasks import legacy_tasks, owned_tasks  # noqa: F401


@pytest.fixture()
def linked_workspace(monorepo, owned_tasks, seed_workspace, monkeypatch):
    from core.routes import term
    root, note, *_ = owned_tasks
    term._save_workspace(monorepo, 'demo', {'id':'demo', 'name':'demo'})
    seed_workspace('other')
    monkeypatch.delenv('LAB_TMUX_PREFIX', raising=False)
    vaults = [{'id':'client','path':monorepo},{'id':'__assistant__','path':root}]
    monkeypatch.setattr(term, '_known_vaults', lambda _:vaults)
    monkeypatch.setattr(term, '_vault_root_for', lambda active, vault:root if vault == '__assistant__' else monorepo)
    monkeypatch.setattr(term, '_vault_id_for_root', lambda active, path:'__assistant__' if path == root else 'client')
    live = []
    monkeypatch.setattr(term, '_tmux_list', lambda *a, **kw:live)
    monkeypatch.setattr(term, '_enrich_session_details', lambda rows:None)
    monkeypatch.setattr(term, '_enrich_agent_session_names', lambda rows:None)
    def forbidden(*a, **kw):
        raise AssertionError('Document linking must never start/stop a process or send input')
    monkeypatch.setattr(term, '_tmux_command', forbidden)
    def session(where=root, workspace='__assistant__', logical='claude', legacy=False, agent='claude'):
        entry = {'name':logical, 'kind':'claude', 'agent':agent, 'agent_session_id':'kept-conversation',
                 'cwd':str(root), 'label':'My agent', 'linked_scope':{'root':str(root)},
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
    def enrich(rows):
        for row in rows:
            row['agent_activity'] = {'state':'completed','completed_at':1234,'completion_id':'done'}
    monkeypatch.setattr(agent_activity, 'enrich', enrich)
    data = client.get('/api/workspace-documents/attention').json()
    assert data['client::demo'][0]['name'] == name
    assert data['__assistant__::__assistant__'][0]['agent_activity']['state'] == 'completed'
    assert 'cwd' not in data['client::demo'][0]
