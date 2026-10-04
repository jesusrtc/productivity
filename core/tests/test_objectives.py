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
    assert Path(data['objectives'][0]['path']).is_dir()
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


def test_five_focus_slots_keep_parked_objective_data_and_reject_stale_writes(monorepo, objective_workspace):
    folder, first = objective_workspace
    for name in ['Two','Three','Four','Five']:
        objectives.mutate(monorepo, 'demo', {'type':'create','name':name})
    before = objectives.load(monorepo, 'demo')
    with pytest.raises(ValueError, match='focus slots'):
        objectives.mutate(monorepo, 'demo', {'type':'create','name':'Six'})
    assert objectives.load(monorepo, 'demo') == before
    data = objectives.mutate(monorepo, 'demo', {'type':'create','name':'Six','replace':first})
    parked = before['focused'][-1]
    assert len(data['focused']) == 5 and len(data['objectives']) == 6 and parked not in data['focused']
    assert data['focused'][1:] == before['focused'][:4]
    data = apply(monorepo, parked, 'focus', replace=data['focused'][0])
    assert data['focused'][0] == parked and len(data['focused']) == 5
    with pytest.raises(ValueError, match='changed elsewhere'):
        objectives.mutate(monorepo, 'demo', {'type':'settings','objective_id':first,'name':'Lost'}, before['revision'])


def test_worktree_membership_and_reserved_colors_are_unique(monorepo, objective_workspace):
    _, first = objective_workspace
    ids = [first]
    for name in ['Two','Three','Four','Five']:
        ids.append(objectives.mutate(monorepo, 'demo', {'type':'create','name':name})['objectives'][-1]['id'])
    for i, oid in enumerate(ids):
        for j in range(4):
            tree = monorepo/f'tree-{i}-{j}'; tree.mkdir()
            data = apply(monorepo, oid, 'worktree', path=str(tree), label=tree.name)
    colors = [t['color'] for o in data['objectives'] for t in o['worktrees']]
    assert len(colors) == len(set(colors)) == 20
    with pytest.raises(ValueError, match='already belongs'):
        apply(monorepo, ids[1], 'worktree', path=str(monorepo/'tree-0-0'))
    data = apply(monorepo, first, 'resource', title='Proposal', kind='link', url='https://example.com')
    r = data['objectives'][0]['resources'][0]
    with pytest.raises(ValueError, match='belong'):
        apply(monorepo, first, 'scope', resource_id=r['id'], worktree=data['objectives'][1]['worktrees'][0]['id'])


def test_focus_insert_shifts_slots_and_keeps_parked_content(monorepo, objective_workspace):
    _, first = objective_workspace
    second = objectives.mutate(monorepo, 'demo', {'type':'create','name':'Second'})['objectives'][-1]['id']
    data = apply(monorepo, second, 'focus', slot=4)
    assert data['focused'] == [first, None, None, None, second]
    data = apply(monorepo, first, 'focus', slot=4)
    assert data['focused'] == [None, None, None, second, first]
    data = apply(monorepo, second, 'resource', title='Retained', kind='document', body='Keep me')
    resource = data['objectives'][1]['resources'][0]
    third = objectives.mutate(monorepo, 'demo', {'type':'create','name':'Third','slot':0})['objectives'][-1]['id']
    data = objectives.payload(monorepo, 'demo')
    assert data['focused'] == [third, None, None, second, first]
    assert data['objectives'][1]['resources'][0]['content']['body'] == 'Keep me'
    for invalid in [-1, 5, True, '1']:
        before = objectives.load(monorepo, 'demo')
        with pytest.raises(ValueError, match='slot'):
            apply(monorepo, second, 'focus', slot=invalid)
        assert objectives.load(monorepo, 'demo') == before
    apply(monorepo, second, 'focus', slot=1)
    assert len({o['color'] for o in objectives.payload(monorepo, 'demo')['objectives']}) == 3


def test_full_slot_insert_reorders_and_colors_follow_position(monorepo, objective_workspace):
    _, first = objective_workspace
    ids = [first]
    for name in ['Two', 'Three', 'Four', 'Five']:
        ids.append(objectives.mutate(monorepo, 'demo', {'type':'create', 'name':name})['objectives'][-1]['id'])
    for index, oid in enumerate(ids):
        for tree_index in range(5):
            folder = monorepo / f'insert-tree-{index}-{tree_index}'
            folder.mkdir()
            apply(monorepo, oid, 'worktree', path=str(folder))
    data = apply(monorepo, ids[-1], 'resource', kind='document', title='Keep', body='Retained after parking')
    saved = data['objectives'][-1]['resources'][0]
    sixth = objectives.mutate(monorepo, 'demo', {'type':'create', 'name':'Six', 'slot':0})['objectives'][-1]['id']
    data = objectives.payload(monorepo, 'demo')
    assert data['focused'] == [sixth, *ids[:4]]
    parked = next(o for o in data['objectives'] if o['id'] == ids[-1])
    assert parked['resources'][0]['id'] == saved['id']
    assert parked['resources'][0]['content']['body'] == 'Retained after parking'
    assert len(parked['worktrees']) == 5 and parked['color'] == '#8b949e'
    data = apply(monorepo, ids[-1], 'focus', slot=2)
    assert data['focused'] == [sixth, ids[0], ids[-1], ids[1], ids[2]]
    data = apply(monorepo, ids[2], 'focus', slot=0)
    assert data['focused'] == [ids[2], sixth, ids[0], ids[-1], ids[1]]
    focused = [next(o for o in data['objectives'] if o['id'] == oid) for oid in data['focused']]
    for slot, objective in enumerate(focused):
        assert objective['color'] == objectives.PALETTES[slot][0]
        assert objective['palette'] == objectives.PALETTES[slot]
        assert [t['color'] for t in objective['worktrees'][:4]] == objectives.PALETTES[slot][:len(objective['worktrees'][:4])]
    colors = [t['color'] for o in focused for t in o['worktrees']]
    assert len(colors) == len(set(colors))
    raw = objectives.registry(monorepo, 'demo').read_bytes()
    objectives.payload(monorepo, 'demo')
    assert objectives.registry(monorepo, 'demo').read_bytes() == raw


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
    data = apply(monorepo, oid, 'worktree', path=str(shortcut), label='fix')
    registry = Path(data['objectives'][0]['manifest_path'])
    saved = storage.read_json(registry)
    saved['worktrees'][0].pop('resolved_path', None)
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
    notebook=data['objectives'][0]['resources'][0]
    body['action'].pop('resource_id')
    body['action']['file']={'root':str(folder/'objectives'/oid),'path':Path(notebook['path']).name}
    response=client.post('/api/objectives',json=body)
    assert response.status_code==200,response.text
    assert response.json()['terminal_links'][saved['session_id']]['file']['path']==Path(notebook['path']).name
    assert term._get_workspace_sessions(monorepo,'demo') == [saved]
    body['action'].pop('file')
    nested = folder/'nested folder';nested.mkdir()
    for root, relative in [(folder,'.'), (folder/'objectives'/oid,'.'), (folder,nested.name)]:
        body['action']['folder']={'root':str(root),'path':relative}
        response=client.post('/api/objectives',json=body)
        assert response.status_code==200,response.text
        assert response.json()['terminal_links'][saved['session_id']]['folder']=={'root':str(root.resolve()),'path':relative}
        assert term._get_workspace_sessions(monorepo,'demo') == [saved]
    before = objectives.load(monorepo,'demo')
    for invalid in ['not a folder target', {'root':4,'path':'.'}, {'root':str(folder),'path':'../../outside'}, {'root':str(folder),'path':notebook['path']},
                    {'root':str(monorepo),'path':'.'}]:
        body['action']['folder']=invalid
        assert client.post('/api/objectives',json=body).status_code==400
        assert objectives.load(monorepo,'demo') == before
    body['action'].pop('folder');body['action']['view']='tasks'
    response=client.post('/api/objectives',json=body)
    assert response.status_code==200,response.text
    assert response.json()['terminal_links'][saved['session_id']]['view']=='tasks'
    before=objectives.load(monorepo,'demo')
    body['action']['file']={'root':str(folder),'path':notebook['path']}
    assert client.post('/api/objectives',json=body).status_code==400
    assert objectives.load(monorepo,'demo')==before
    body['action'].pop('file')
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
    assert doc.read_text() == '# Original' and not list((folder/'objectives').rglob('*.md'))
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
    assert note.read_bytes()==original and not list((folder/'objectives').rglob('*.md'))
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
