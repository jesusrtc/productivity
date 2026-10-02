"""Objective ownership, task details, focus slots and independent terminal links."""
import json
from pathlib import Path
from types import SimpleNamespace
import threading

import pytest
from lab import assistant_documents, objectives, storage
from .test_assistant_documents_unified import library  # noqa: F401
from .test_workspace_documents import linked_workspace, link_document, link_terminal  # noqa: F401
from .test_assistant_document_tasks import legacy_tasks, owned_tasks  # noqa: F401


@pytest.fixture()
def objective_workspace(monorepo, seed_workspace):
    folder = seed_workspace()
    before = {name:(folder/name).read_bytes() for name in ['workspace.json','tasks.json']}
    data = objectives.mutate(monorepo, 'demo', {'type':'create','name':'Phone recovery'})
    yield folder, data['objectives'][0]['id']
    assert {name:(folder/name).read_bytes() for name in before} == before


def apply(root, oid, type_, **fields):
    return objectives.mutate(root, 'demo', {'type':type_, 'objective_id':oid, **fields})


def test_tasks_always_have_details_and_nested_subtabs_preserve_siblings(monorepo, objective_workspace):
    folder, oid = objective_workspace
    data = apply(monorepo, oid, 'task', title='Verify parser', due='2026-10-04')
    parent = data['objectives'][0]['tasks'][0]
    data = apply(monorepo, oid, 'task', title='Malformed input', parent_id=parent['id'])
    o = data['objectives'][0]; child = o['tasks'][0]['children'][0]; resource = o['resources'][0]
    assert child['document_id'] == parent['document_id'] == resource['id']
    assert resource['content']['tabs'][1]['parent']['id'] == parent['tab_id']
    original = resource['content']['tabs'][0]['body']
    data = apply(monorepo, oid, 'document', resource_id=resource['id'], tab_id=child['tab_id'],
                 document_revision=resource['content']['revision'], body='Child evidence')
    assert data['objectives'][0]['resources'][0]['content']['tabs'][0]['body'] == original
    assert data['objectives'][0]['resources'][0]['content']['tabs'][1]['body'] == 'Child evidence'
    with pytest.raises(ValueError, match='changed elsewhere'):
        apply(monorepo, oid, 'document', resource_id=resource['id'], tab_id=child['tab_id'],
              document_revision=resource['content']['revision'], body='Overwrite')
    with pytest.raises(ValueError, match='still needs'):
        apply(monorepo, oid, 'remove-resource', resource_id=resource['id'])
    data = apply(monorepo, oid, 'task-update', task_id=parent['id'], done=True)
    assert all(c['done'] for c in data['objectives'][0]['tasks'][0]['children'])


def test_three_focus_slots_keep_parked_objective_data_and_reject_stale_writes(monorepo, objective_workspace):
    folder, first = objective_workspace
    for name in ['Two','Three']:
        objectives.mutate(monorepo, 'demo', {'type':'create','name':name})
    before = objectives.load(monorepo, 'demo')
    with pytest.raises(ValueError, match='focus slots'):
        objectives.mutate(monorepo, 'demo', {'type':'create','name':'Four'})
    assert objectives.load(monorepo, 'demo') == before
    data = objectives.mutate(monorepo, 'demo', {'type':'create','name':'Four','replace':first})
    assert len(data['focused']) == 3 and len(data['objectives']) == 4 and first not in data['focused']
    last = data['focused'][0]
    data = apply(monorepo, first, 'focus', replace=last)
    assert first in data['focused'] and last not in data['focused']
    with pytest.raises(ValueError, match='changed elsewhere'):
        objectives.mutate(monorepo, 'demo', {'type':'settings','objective_id':first,'name':'Lost'}, before['revision'])


def test_worktree_membership_and_reserved_colors_are_unique(monorepo, objective_workspace):
    _, first = objective_workspace
    ids = [first]
    for name in ['Two','Three']:
        ids.append(objectives.mutate(monorepo, 'demo', {'type':'create','name':name})['objectives'][-1]['id'])
    for i, oid in enumerate(ids):
        for j in range(4):
            tree = monorepo/f'tree-{i}-{j}'; tree.mkdir()
            data = apply(monorepo, oid, 'worktree', path=str(tree), label=tree.name)
    colors = [t['color'] for o in data['objectives'] for t in o['worktrees']]
    assert len(colors) == len(set(colors)) == 12
    with pytest.raises(ValueError, match='already belongs'):
        apply(monorepo, ids[1], 'worktree', path=str(monorepo/'tree-0-0'))
    data = apply(monorepo, first, 'resource', title='Proposal', kind='link', url='https://example.com')
    r = data['objectives'][0]['resources'][0]
    with pytest.raises(ValueError, match='belong'):
        apply(monorepo, first, 'scope', resource_id=r['id'], worktree=data['objectives'][1]['worktrees'][0]['id'])


def test_owned_rename_keeps_ids_and_task_references_and_unlink_preserves_files(monorepo, objective_workspace):
    folder, oid = objective_workspace
    data = apply(monorepo, oid, 'task', title='One')
    r = data['objectives'][0]['resources'][0]; old = folder/r['path']; tab = r['content']['tabs'][0]
    data = apply(monorepo, oid, 'rename', resource_id=r['id'], title='Evidence')
    updated = data['objectives'][0]['resources'][0]
    assert not old.exists() and (folder/updated['path']).name == 'Evidence.md'
    assert updated['id'] == r['id'] and updated['content']['tabs'][0]['id'] == tab['id']
    data = apply(monorepo, oid, 'rename', resource_id=r['id'], tab_id=tab['id'], title='Renamed details')
    assert data['objectives'][0]['resources'][0]['content']['tabs'][0]['title'] == 'Renamed details'
    data = apply(monorepo, oid, 'resource', title='Analysis', kind='notebook')
    nb = data['objectives'][0]['resources'][-1]; original = (folder/nb['path']).read_bytes()
    data = apply(monorepo, oid, 'rename', resource_id=nb['id'], title='Volume')
    new = data['objectives'][0]['resources'][-1]
    assert new['path'].endswith('/Volume.ipynb') and (folder/new['path']).read_bytes() == original
    apply(monorepo, oid, 'remove-resource', resource_id=new['id'])
    assert (folder/new['path']).is_file()


def test_legacy_worktree_paths_resolve_for_terminal_grouping_without_registry_writes(monorepo, objective_workspace):
    folder, oid = objective_workspace
    checkout = monorepo/'actual-checkout'; checkout.mkdir()
    shortcut = monorepo/'shortcut-checkout'; shortcut.symlink_to(checkout, target_is_directory=True)
    apply(monorepo, oid, 'worktree', path=str(shortcut), label='fix')
    registry = objectives.registry(monorepo, 'demo')
    saved = storage.read_json(registry)
    saved['objectives'][0]['worktrees'][0].pop('resolved_path')
    storage.write_json(registry, saved)
    before = registry.read_bytes()
    tree = objectives.payload(monorepo, 'demo')['objectives'][0]['worktrees'][0]
    assert tree['path'] == str(shortcut) and tree['resolved_path'] == str(checkout)
    assert registry.read_bytes() == before


def test_invalid_paths_urls_and_document_links_do_not_write(monorepo, objective_workspace):
    folder, oid = objective_workspace
    before = objectives.load(monorepo,'demo')
    for action in [dict(type='resource',kind='link',title='Bad',url='javascript:alert(1)'),
                   dict(type='resource',kind='file',title='Bad',path='../../private.md'),
                   dict(type='task',title='Bad',document_id='missing'),
                   dict(type='terminal',session_id='saved',file={'root':str(monorepo),'path':'outside'})]:
        with pytest.raises(ValueError):
            apply(monorepo,oid,**{'type_':action.pop('type')},**action)
        assert objectives.load(monorepo,'demo') == before
    outside = monorepo/'outside.md'; outside.write_text('private')
    with pytest.raises(ValueError):
        objectives.document(folder, {'path':'../../outside.md','kind':'document'})


def test_terminal_resource_links_never_change_session_metadata(client, monorepo, seed_workspace):
    from core.routes import term
    folder = seed_workspace()
    term._upsert_workspace_session(monorepo,'demo',{'name':'shell','kind':'terminal','cwd':str(folder),'agent_session_id':'keep'})
    saved = term._get_workspace_sessions(monorepo,'demo')[0]
    data = client.post('/api/objectives',json={'workspace_id':'demo','action':{'type':'create','name':'One'}}).json()
    oid = data['objectives'][0]['id']
    data = apply(monorepo,oid,'resource',kind='notebook',title='Analysis'); rid=data['objectives'][0]['resources'][0]['id']
    body = {'workspace_id':'demo','action':{'type':'terminal','objective_id':oid,'session_id':saved['session_id'],'resource_id':rid}}
    assert client.post('/api/objectives',json=body).status_code == 200
    assert term._get_workspace_sessions(monorepo,'demo') == [saved]
    body['action']['session_id'] = 'a-terminal-in-another-workspace'
    assert client.post('/api/objectives',json=body).status_code == 400
    assert term._get_workspace_sessions(monorepo,'demo') == [saved]


def test_existing_workspace_import_copies_references_not_assistant_content(monorepo, seed_workspace):
    folder=seed_workspace(); tree=monorepo/'tree';tree.mkdir()
    metadata=storage.read_json(folder/'workspace.json');metadata['worktrees']=[{'dir':str(tree),'branch':'fix','repo':str(tree)}]
    storage.write_json(folder/'workspace.json',metadata)
    original=(folder/'workspace.json').read_bytes(); doc=folder/'docs/original.md';doc.write_text('# Original')
    storage.write_json(folder/'.lab/document-links.json',{'documents':[{'assistant_root':str(monorepo/'assistant'),'document_id':'doc-id','title':'Assistant reference'}]})
    reference=(folder/'.lab/document-links.json').read_bytes()
    data=objectives.mutate(monorepo,'demo',{'type':'create','name':'One','import_existing':True})
    o=data['objectives'][0]
    assert o['worktrees'][0]['path'] == str(tree)
    assert [r['kind'] for r in o['resources']] == ['assistant','file']
    assert doc.read_text() == '# Original' and not (folder/'objectives').exists()
    assert (folder/'workspace.json').read_bytes() == original and (folder/'.lab/document-links.json').read_bytes() == reference


def test_idle_notebook_rename_rekeys_live_kernel_and_busy_rename_is_rejected(client, monorepo, seed_workspace):
    from core import notebook_kernel as nk
    folder=seed_workspace();data=objectives.mutate(monorepo,'demo',{'type':'create','name':'One'});oid=data['objectives'][0]['id']
    data=apply(monorepo,oid,'resource',kind='notebook',title='Analysis');r=data['objectives'][0]['resources'][0]
    old=folder/r['path']; relative=old.relative_to(monorepo).as_posix(); busy=threading.Event()
    session=SimpleNamespace(rel_path=relative,process=SimpleNamespace(busy=busy))
    key=(str(monorepo.resolve()),relative); nk._sessions[key]=session
    body={'workspace_id':'demo','action':{'type':'rename','objective_id':oid,'resource_id':r['id'],'title':'Renamed'}}
    try:
        busy.set();response=client.post('/api/objectives',json=body);assert response.status_code==400 and old.exists()
        busy.clear();response=client.post('/api/objectives',json=body);assert response.status_code==200,response.text
        new=response.json()['objectives'][0]['resources'][0]
        newkey=(str(monorepo.resolve()),(folder/new['path']).relative_to(monorepo).as_posix())
        assert key not in nk._sessions and nk._sessions[newkey] is session and session.rel_path==newkey[1]
    finally:
        for k in list(nk._sessions):
            if nk._sessions[k] is session: nk._sessions.pop(k)


def test_assistant_references_expose_subtabs_without_editing_originals(client, monorepo, seed_workspace, library):
    root, _, note, content, *_ = library
    folder = seed_workspace('objective-demo')
    original = note.read_bytes()
    data = client.post('/api/objectives',json={'workspace_id':'objective-demo','action':{'type':'create','name':'One'}}).json()
    oid = data['objectives'][0]['id']
    response = client.post('/api/objectives',json={'workspace_id':'objective-demo','action':{
        'type':'resource','objective_id':oid,'kind':'assistant','title':'Reference',
        'assistant_root':str(root),'document_id':note.stem}})
    assert response.status_code == 200,response.text
    r=response.json()['objectives'][0]['resources'][0]
    assert r['kind']=='assistant' and r['title']=='Guide' and r['content']['tabs']
    assert note.read_bytes()==original and not (folder/'objectives').exists()
    response=client.get('/api/objectives?workspace_id=objective-demo')
    assert response.status_code==200 and note.read_bytes()==original


def test_shared_terminal_association_keeps_assistant_owner_and_launch_folder(client, linked_workspace, monorepo):
    from core.routes import term
    root, note, live, session = linked_workspace
    session(); link_terminal(client,note); link_document(client,root,note)
    before = term._get_workspace_sessions(root,'__assistant__')
    data = objectives.mutate(monorepo,'demo',{'type':'create','name':'One'});oid=data['objectives'][0]['id']
    data = apply(monorepo,oid,'resource',kind='document',title='Workspace evidence')
    body={'workspace_id':'demo','vault':'client','action':{'type':'terminal','objective_id':oid,
        'session_id':before[0]['session_id'],'resource_id':data['objectives'][0]['resources'][0]['id'],
        'source':{'workspace_id':'__assistant__','vault':'__assistant__','logical_name':'claude'}}}
    response=client.post('/api/objectives',json=body)
    assert response.status_code==200,response.text
    assert term._get_workspace_sessions(root,'__assistant__')==before
    assert term._get_workspace_sessions(monorepo,'demo')==[]
    assert len(live)==1
