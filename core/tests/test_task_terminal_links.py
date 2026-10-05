"""Task links reuse durable sessions without changing work or process count."""
from concurrent.futures import ThreadPoolExecutor
import threading
import time

import pytest
from fastapi import HTTPException
from lab import assistant_tasks as tasks

from .test_assistant_document_tasks import legacy_tasks, owned_tasks  # noqa: F401


@pytest.fixture()
def terminals(monorepo, monkeypatch, seed_workspace, owned_tasks):
    from core.routes import term
    for workspace in ['demo','other']:
        if workspace != "demo":
            seed_workspace(workspace)
        else:
            term._save_workspace(monorepo,workspace,{"id":workspace,"name":workspace})
        term._upsert_workspace_session(monorepo, workspace, {
            'name':workspace, 'kind':'terminal', 'agent_session_id':'keep-' + workspace,
            'label':'My terminal', 'linked_file':{'root':str(monorepo),'path':workspace + '.md'},
            'linked_scope':{'root':str(monorepo)}})
    monkeypatch.setattr(term, '_known_vaults', lambda _: [{'id':monorepo.name,'path':monorepo}])
    monkeypatch.setattr(term, '_load_meta', lambda _: {})
    monkeypatch.setattr(term, '_save_meta', lambda *_: None)
    names = [term._tmux_name_for(w,w,monorepo) for w in ['demo','other']]
    live = [{'name':name} for name in names]
    monkeypatch.setattr(term,'_tmux_list',lambda *a,**k:live)
    def forbidden(*a,**k):
        raise AssertionError('Linking must not start, stop, or send input to a process')
    monkeypatch.setattr(term,'_tmux_command',forbidden)
    return live


def test_task_transfer_reopen_and_unlink_preserve_session_and_document(client, terminals, owned_tasks, monorepo):
    from core.routes import term
    root,note,*_=owned_tasks
    task=tasks.view(root,note.stem)['tasks'][0]
    before=note.read_bytes()
    def patch(workspace, link):
        result=client.patch('/api/term/sessions/metadata',json={
            'workspace_id':workspace,'name':workspace,'linked_task':link})
        assert result.status_code==200,result.text
        return result.json()
    link={'document_id':note.stem,'task_id':task['id']}
    patch('demo',link)
    listed=client.get('/api/term/task-terminals',params={'document_id':note.stem}).json()
    assert len(listed)==1 and listed[0]['state']=='running'
    assert listed[0]['logical_name']=='demo' and listed[0]['linked_task']['task_id']==task['id']
    transferred=patch('other',link)
    assert len(transferred['displaced'])==1
    previous=transferred['displaced'][0]['session']
    assert 'linked_task' not in previous and previous['agent_session_id']=='keep-demo'
    assert previous['label']=='My terminal' and previous['linked_file']['path']=='demo.md'
    # Missing processes remain linked but reading never wakes them.
    terminals.clear()
    listed=client.get('/api/term/task-terminals',params={'document_id':note.stem}).json()
    assert len(listed)==1 and listed[0]['state']=='stopped'
    assert client.get('/api/term/task-terminals').json()==[]
    patch('other',None)
    assert client.get('/api/term/task-terminals',params={'document_id':note.stem}).json()==[]
    for workspace in ['demo','other']:
        saved=term._get_workspace_sessions(monorepo,workspace)[0]
        assert saved['agent_session_id']=='keep-' + workspace and saved['linked_scope']
        assert saved['linked_file'] and 'linked_task' not in saved
    assert note.read_bytes()==before


def test_invalid_or_unauthorized_task_transfer_writes_nothing(client, terminals, owned_tasks, monorepo, monkeypatch):
    from core.routes import term
    root,note,*_=owned_tasks
    before=term._load_workspace(monorepo,'demo')
    for document,task in [(note.stem,'missing'),('../outside',None),('missing',None)]:
        response=client.patch('/api/term/sessions/metadata',json={
            'workspace_id':'demo','name':'demo','label':'Do not write',
            'linked_task':{'document_id':document,'task_id':task}})
        assert response.status_code==400,response.text
        assert term._load_workspace(monorepo,'demo')==before
    monkeypatch.setattr(term.auth,'require_admin',lambda _: (_ for _ in ()).throw(HTTPException(403,'admin required')))
    response=client.patch('/api/term/sessions/metadata',json={'workspace_id':'demo','name':'demo',
        'linked_task':{'document_id':note.stem}})
    assert response.status_code==403
    assert term._load_workspace(monorepo,'demo')==before


def test_drop_requires_the_original_document_database_and_path(client, terminals, owned_tasks, monorepo):
    from core.routes import term
    root,note,*_=owned_tasks
    before=term._load_workspace(monorepo,'demo')
    link={'document_id':note.stem,'assistant_root':str(root),'path':note.relative_to(root).as_posix()}
    for override in [{'assistant_root':str(root.parent/'other-assistant')}, {'path':'documents/different.md'}]:
        response=client.patch('/api/term/sessions/metadata',json={
            'workspace_id':'demo','name':'demo','linked_task':{**link,**override}})
        assert response.status_code==409,response.text
        assert term._load_workspace(monorepo,'demo')==before
    response=client.patch('/api/term/sessions/metadata',json={
        'workspace_id':'demo','name':'demo','linked_task':link})
    assert response.status_code==200,response.text
    saved=response.json()['session']
    assert saved['linked_task']['document_id']==note.stem
    assert saved['label']==before['sessions'][0]['label']


def test_explicit_task_drop_renames_to_canonical_title(client, terminals, owned_tasks, monorepo):
    from core.routes import term
    root,note,*_ = owned_tasks
    child=next(task for task in tasks.view(root,note.stem)['tasks'] if task.get('parent_id'))
    before=term._get_workspace_sessions(monorepo,'demo')[0]
    response=client.patch('/api/term/sessions/metadata',json={'workspace_id':'demo','name':'demo',
        'linked_task':{'document_id':note.stem,'task_id':child['id']},'rename_to_task':True})
    assert response.status_code==200,response.text
    saved=response.json()['session']
    assert saved['label']==child['title']
    assert {key:value for key,value in saved.items() if key not in {'label','linked_task'}}=={key:value for key,value in before.items() if key not in {'label','linked_task'}}
    assert len(terminals)==2


def test_series_link_keeps_its_identity_and_title(client, terminals, owned_tasks):
    from lab import assistant_records as records
    root,*_=owned_tasks
    series=records.create(root,'note','Weekly review',note_type='series')
    latest=records.create(root,'note','Different meeting title',note_type='meeting',series=series.stem,date='2026-09-30')
    before={path:path.read_bytes() for path in (series,latest)}
    response=client.patch('/api/term/sessions/metadata',json={
        'workspace_id':'demo','name':'demo','linked_task':{
            'document_id':series.stem,'assistant_root':str(root),'path':series.relative_to(root).as_posix()}})
    assert response.status_code==200,response.text
    link=response.json()['session']['linked_task']
    assert link['document_id']==series.stem and link['title']=='Weekly review'
    assert all(path.read_bytes()==contents for path,contents in before.items())


def test_document_and_task_links_are_distinct_and_simultaneous_assignment_has_one_owner(client, terminals, owned_tasks, monorepo, monkeypatch):
    from core.routes import term
    root,note,*_=owned_tasks
    monkeypatch.setattr(term.auth,'request_root',lambda _:monorepo)
    monkeypatch.setattr(term,'_require_workspace_access',lambda *a:{})
    monkeypatch.setattr(term.auth,'require_admin',lambda _: {})
    task=tasks.view(root,note.stem)['tasks'][0]
    def assign(workspace, task_id=None):
        return term.update_session_metadata(term.SessionMetadata(workspace_id=workspace,name=workspace,
            linked_task=term.LinkedTask(document_id=note.stem,task_id=task_id)),None)
    assign('demo')
    assign('other',task['id'])
    assert len(client.get('/api/term/task-terminals',params={'document_id':note.stem}).json())==2
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert all(row['ok'] for row in pool.map(assign,['demo','other']))
    links=[s.get('linked_task') for w in ['demo','other'] for s in term._get_workspace_sessions(monorepo,w)]
    assert sum(bool(link) for link in links)==1


def test_document_terminal_lock_timeout_does_not_exhaust_workers(client, terminals, owned_tasks, monkeypatch):
    from core import fsguard
    from core.routes import term

    _, note, *_ = owned_tasks
    lock = threading.RLock()
    monkeypatch.setattr(term, '_SESSION_METADATA_LOCK', lock)
    monkeypatch.setenv('LAB_FS_TIMEOUT_SECONDS', '.03')
    with lock:
        response = client.get('/api/term/task-terminals', params={'document_id':note.stem})
        assert response.status_code == 503
        deadline = time.monotonic() + 1
        while fsguard._inflight and time.monotonic() < deadline:
            time.sleep(.01)
        assert fsguard._inflight == 0, 'the timed-out reader still holds a filesystem worker'
    monkeypatch.setenv('LAB_FS_TIMEOUT_SECONDS', '10')
    assert client.get('/api/term/task-terminals', params={'document_id':note.stem}).status_code == 200
