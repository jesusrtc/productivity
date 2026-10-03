"""Task assets reference original content and terminals retain their owners."""
import pytest
from lab import objectives
from .test_assistant_documents_unified import library  # noqa: F401


@pytest.fixture()
def task_workspace(monorepo, seed_workspace):
    from core.routes import term
    folder = seed_workspace()
    term._upsert_workspace_session(monorepo,'demo',{'name':'task-shell','kind':'terminal','cwd':str(folder),'agent_session_id':'preserve'})
    before = {name:(folder/name).read_bytes() for name in ['workspace.json','tasks.json']}
    oid = objectives.mutate(monorepo, 'demo', {'type':'create', 'name':'Tasks'})['objectives'][0]['id']
    data = objectives.mutate(monorepo, 'demo', {'type':'task', 'objective_id':oid, 'title':'Verify the fix'})
    task = data['objectives'][0]['tasks'][0]
    yield folder, oid, task
    assert {name:(folder/name).read_bytes() for name in before} == before


def apply(root, oid, operation, **fields):
    return objectives.mutate(root, 'demo', {'type':operation, 'objective_id':oid, **fields})


def test_task_assets_keep_scope_subtabs_and_original_content(monorepo, task_workspace):
    folder, oid, task = task_workspace
    tree = apply(monorepo, oid, 'worktree', path=str(folder))['objectives'][0]['worktrees'][0]
    resource = apply(monorepo, oid, 'resource', kind='notebook', title='Analysis', worktree=tree['id'])['objectives'][0]['resources'][-1]
    original = (folder/resource['path']).read_bytes()
    data = apply(monorepo, oid, 'task-asset', task_id=task['id'], resource_id=resource['id'])
    asset = data['objectives'][0]['tasks'][0]['assets'][0]
    assert asset['id'] and asset['resource_id'] == resource['id']
    data = apply(monorepo, oid, 'task-asset', task_id=task['id'], resource_id=resource['id'])
    assert data['objectives'][0]['tasks'][0]['assets'] == [asset]
    data = apply(monorepo, oid, 'task-asset', task_id=task['id'], reference={'kind':'file','title':'Analysis.ipynb','file_root':str(folder),'path':resource['path']})
    assert data['objectives'][0]['tasks'][0]['assets'] == [asset]
    assert len(data['objectives'][0]['resources']) == 2
    data = apply(monorepo, oid, 'task-update', task_id=task['id'], icon_asset_id=asset['id'])
    assert data['objectives'][0]['tasks'][0]['icon_asset_id'] == asset['id']
    assert data['objectives'][0]['resources'][-1]['worktree'] == tree['id']
    assert (folder/resource['path']).read_bytes() == original
    # Required details are implicit and are never duplicated or detachable.
    data = apply(monorepo, oid, 'task-asset', task_id=task['id'], resource_id=task['document_id'], tab_id=task['tab_id'])
    assert data['objectives'][0]['tasks'][0]['assets'] == [asset]
    data = apply(monorepo, oid, 'task', title='Check output', parent_id=task['id'])
    child = data['objectives'][0]['tasks'][0]['children'][0]
    data = apply(monorepo, oid, 'task-asset', task_id=child['id'], resource_id=task['document_id'], tab_id=task['tab_id'])
    assert data['objectives'][0]['tasks'][0]['children'][0]['assets'][0]['tab_id'] == task['tab_id']
    assert data['objectives'][0]['tasks'][0]['assets'] == [asset]


def test_existing_files_and_folders_attach_without_copying(monorepo, task_workspace):
    folder, oid, task = task_workspace
    notebook = folder/'existing.ipynb'
    notebook.write_text('{"cells":[],"metadata":{},"nbformat":4,"nbformat_minor":5}')
    original = notebook.read_bytes()
    ref = {'kind':'file','title':'Existing notebook','file_root':str(folder),'path':notebook.name}
    data = apply(monorepo, oid, 'task-asset', task_id=task['id'], reference=ref)
    imported = data['objectives'][0]['resources'][-1]
    assert imported['kind'] == 'file' and imported['path'] == notebook.name
    data = apply(monorepo, oid, 'task-asset', task_id=task['id'], reference=ref)
    assert len(data['objectives'][0]['resources']) == 2
    assert len(data['objectives'][0]['tasks'][0]['assets']) == 1
    data = apply(monorepo, oid, 'task-asset', task_id=task['id'], folder={'root':str(folder),'path':'.'})
    assert data['objectives'][0]['tasks'][0]['assets'][-1]['folder'] == {'root':str(folder.resolve()),'path':'.'}
    worktree = monorepo/'task-worktree';worktree.mkdir()
    apply(monorepo, oid, 'worktree', path=str(worktree), label='fix')
    data = apply(monorepo, oid, 'task-asset', task_id=task['id'], folder={'root':str(worktree),'path':'.'})
    assert data['objectives'][0]['tasks'][0]['assets'][-1]['folder']['root'] == str(worktree)
    assert notebook.read_bytes() == original and len(list((folder/'objectives'/oid).glob('*.ipynb'))) == 0


def test_invalid_assets_icons_and_terminal_targets_are_atomic(monorepo, task_workspace):
    folder, oid, task = task_workspace
    other = objectives.mutate(monorepo, 'demo', {'type':'create','name':'Other'})['objectives'][-1]['id']
    foreign = apply(monorepo, other, 'resource', kind='document', title='Foreign')['objectives'][-1]['resources'][0]
    actions = [
        ('task-asset', {'resource_id':'missing'}),
        ('task-asset', {'resource_id':foreign['id']}),
        ('task-asset', {'resource_id':task['document_id'],'tab_id':'missing'}),
        ('task-asset', {'reference':{'kind':'file','title':'Escape','file_root':str(folder),'path':'../../outside'}}),
        ('task-asset', {'folder':{'root':str(monorepo),'path':'.'}}),
        ('task-asset', {'folder':{'root':str(folder),'path':'.'},'resource_id':task['document_id']}),
        ('task-remove-asset', {'asset_id':'details'}),
        ('task-update', {'icon_asset_id':'missing'}),
        ('terminal', {'session_id':'terminal','resource_id':task['document_id']}),
        ('terminal', {'session_id':'terminal','view':'tasks'}),
    ]
    for operation, fields in actions:
        before = objectives.registry(monorepo,'demo').read_bytes()
        with pytest.raises(ValueError):
            apply(monorepo, oid, operation, task_id=task['id'], **fields)
        assert objectives.registry(monorepo,'demo').read_bytes() == before
    with pytest.raises(ValueError, match='Task not found'):
        apply(monorepo, oid, 'terminal', task_id='missing', session_id='terminal')


def test_detaching_and_unlinking_assets_reset_only_their_icon(monorepo, task_workspace):
    folder, oid, task = task_workspace
    resource = apply(monorepo, oid, 'resource', kind='document', title='Evidence')['objectives'][0]['resources'][-1]
    data = apply(monorepo, oid, 'task-asset', task_id=task['id'], resource_id=resource['id'])
    asset = data['objectives'][0]['tasks'][0]['assets'][0]
    apply(monorepo, oid, 'task-update', task_id=task['id'], icon_asset_id=asset['id'])
    data = apply(monorepo, oid, 'task-remove-asset', task_id=task['id'], asset_id=asset['id'])
    assert data['objectives'][0]['tasks'][0]['assets'] == []
    assert 'icon_asset_id' not in data['objectives'][0]['tasks'][0]
    assert (folder/resource['path']).is_file()
    data = apply(monorepo, oid, 'resource', kind='link', title='Docs', url='https://example.com/', sublinks=[{'title':'Tab','url':'https://example.com/?tab=one'}])
    link = data['objectives'][0]['resources'][-1]
    data = apply(monorepo, oid, 'task-asset', task_id=task['id'], resource_id=link['id'], sub_link_id=link['sublinks'][0]['id'])
    asset = data['objectives'][0]['tasks'][0]['assets'][0]
    apply(monorepo, oid, 'task-update', task_id=task['id'], icon_asset_id=asset['id'])
    data = apply(monorepo, oid, 'link-remove-sublink', resource_id=link['id'], sub_link_id=link['sublinks'][0]['id'])
    assert data['objectives'][0]['tasks'][0]['assets'] == []
    assert 'icon_asset_id' not in data['objectives'][0]['tasks'][0]
    apply(monorepo, oid, 'task-asset', task_id=task['id'], resource_id=resource['id'])
    data = apply(monorepo, oid, 'remove-resource', resource_id=resource['id'])
    assert data['objectives'][0]['tasks'][0]['assets'] == [] and (folder/resource['path']).is_file()


def test_task_terminal_and_assistant_assets_preserve_original_owners(client, monorepo, task_workspace, library):
    from core.routes import term
    folder, oid, task = task_workspace
    root, _, note, *_ = library
    original = note.read_bytes()
    data = client.post('/api/objectives',json={'workspace_id':'demo','action':{'type':'task-asset','objective_id':oid,'task_id':task['id'],
        'reference':{'kind':'assistant','title':'Reference','assistant_root':str(root),'document_id':note.stem}}})
    assert data.status_code == 200, data.text
    ref = data.json()['objectives'][0]['resources'][-1]
    assert ref['kind'] == 'assistant' and ref['document_id'] == note.stem and note.read_bytes() == original
    assert len(list((folder/'objectives'/oid).glob('*.md'))) == 1
    action = {'type':'task-asset','objective_id':oid,'task_id':task['id'],'resource_id':ref['id'],'tab_id':ref['content']['tabs'][0]['id']}
    response = client.post('/api/objectives',json={'workspace_id':'demo','action':action})
    assert response.status_code == 200 and note.read_bytes() == original
    assert response.json()['objectives'][0]['tasks'][0]['assets'][-1]['tab_id'] == action['tab_id']
    starred = client.post('/api/objectives',json={'workspace_id':'demo','action':{**action,'type':'asset-star','starred':True}})
    assert starred.status_code == 200 and note.read_bytes() == original
    assert starred.json()['objectives'][0]['shared_assets'][0]['tab_id'] == action['tab_id']
    before_registry = objectives.registry(monorepo,'demo').read_bytes()
    for operation, fields in [('task-asset',{}),('asset-star',{'starred':True}),('asset-bucket',{'bucket':'archive'})]:
        response = client.post('/api/objectives',json={'workspace_id':'demo','action':{**action,**fields,'type':operation,'tab_id':'missing'}})
        assert response.status_code == 400 and objectives.registry(monorepo,'demo').read_bytes() == before_registry
    before = term._get_workspace_sessions(monorepo,'demo')
    action = {'type':'terminal','objective_id':oid,'task_id':task['id'],'session_id':before[0]['session_id']}
    response = client.post('/api/objectives',json={'workspace_id':'demo','action':action})
    assert response.status_code == 200, response.text
    assert response.json()['terminal_links'][before[0]['session_id']]['task_id'] == task['id']
    assert term._get_workspace_sessions(monorepo,'demo') == before and note.read_bytes() == original
    stale = response.json()['revision']
    apply(monorepo, oid, 'task-update', task_id=task['id'], title='Newer')
    response = client.post('/api/objectives',json={'workspace_id':'demo','expected':stale,'action':action})
    assert response.status_code == 409 and term._get_workspace_sessions(monorepo,'demo') == before


def test_shared_stars_and_archive_keep_original_content(monorepo, task_workspace):
    folder, oid, task = task_workspace
    data = apply(monorepo, oid, 'resource', kind='notebook', title='Evidence')
    resource = data['objectives'][0]['resources'][-1]
    original = (folder/resource['path']).read_bytes()
    data = apply(monorepo, oid, 'task-asset', task_id=task['id'], resource_id=resource['id'], choose_icon=True)
    attached = data['objectives'][0]['tasks'][0]['assets'][0]
    assert data['objectives'][0]['tasks'][0]['icon_asset_id'] == attached['id']
    data = apply(monorepo, oid, 'asset-star', resource_id=resource['id'], starred=True)
    assert data['objectives'][0]['shared_assets'][0]['resource_id'] == resource['id']
    data = apply(monorepo, oid, 'asset-star', resource_id=resource['id'], starred=False)
    assert data['objectives'][0]['shared_assets'] == []
    assert data['objectives'][0]['tasks'][0]['assets'] == [attached]
    apply(monorepo, oid, 'asset-star', resource_id=resource['id'], starred=True)
    data = apply(monorepo, oid, 'asset-bucket', resource_id=resource['id'], bucket='archive')
    owner = data['objectives'][0]
    assert owner['shared_assets'] == [] and owner['tasks'][0]['assets'] == []
    assert 'icon_asset_id' not in owner['tasks'][0]
    assert owner['archived_assets'][0]['resource_id'] == resource['id']
    data = apply(monorepo, oid, 'task-asset', task_id=task['id'], resource_id=resource['id'], choose_icon=True)
    assert data['objectives'][0]['archived_assets'] == []
    data = apply(monorepo, oid, 'asset-bucket', resource_id=resource['id'], bucket='unassigned')
    assert data['objectives'][0]['tasks'][0]['assets'] == []
    assert (folder/resource['path']).read_bytes() == original


def test_shared_exact_tabs_and_folder_references_are_validated(monorepo, task_workspace):
    folder, oid, task = task_workspace
    # Legacy registries need no rewrite merely to display the new buckets.
    before = objectives.registry(monorepo,'demo').read_bytes()
    owner = objectives.payload(monorepo,'demo')['objectives'][0]
    assert owner['shared_assets'] == owner['archived_assets'] == owner['asset_shelf'] == []
    assert objectives.registry(monorepo,'demo').read_bytes() == before
    apply(monorepo, oid, 'asset-star', resource_id=task['document_id'], tab_id=task['tab_id'], starred=True)
    for operation, fields in [
        ('asset-bucket', {'resource_id':task['document_id'],'tab_id':task['tab_id'],'bucket':'archive'}),
        ('asset-bucket', {'resource_id':task['document_id'],'bucket':'unassigned'}),
        ('asset-star', {'folder':{'root':str(monorepo),'path':'.'},'starred':True}),
        ('asset-star', {'resource_id':task['document_id'],'starred':'yes'}),
        ('task-asset', {'task_id':task['id'],'resource_id':task['document_id'],'choose_icon':'yes'}),
        ('asset-bucket', {'resource_id':task['document_id'],'bucket':'missing'}),
    ]:
        before = objectives.registry(monorepo,'demo').read_bytes()
        with pytest.raises(ValueError):
            apply(monorepo, oid, operation, **fields)
        assert objectives.registry(monorepo,'demo').read_bytes() == before
    source = folder/'existing.sql';source.write_text('SELECT 1;')
    data = apply(monorepo, oid, 'asset-star', reference={'kind':'file','title':'Query','file_root':str(folder),'path':source.name}, starred=True)
    query = data['objectives'][0]['resources'][-1]
    assert query['kind'] == 'file' and source.read_text() == 'SELECT 1;'
    data = apply(monorepo, oid, 'asset-star', folder={'root':str(folder),'path':'.'}, starred=True)
    assert data['objectives'][0]['asset_shelf'][0]['folder']['root'] == str(folder)
    data = apply(monorepo, oid, 'asset-star', folder={'root':str(folder),'path':'.'}, starred=False)
    assert any(a.get('resource_id') == query['id'] for a in data['objectives'][0]['shared_assets'])
    assert data['objectives'][0]['asset_shelf'][0]['folder']['path'] == '.'


def test_removing_sublinks_prunes_shared_and_archived_references(monorepo, task_workspace):
    _, oid, task = task_workspace
    data = apply(monorepo, oid, 'resource', kind='link', title='Document', url='https://example.com/',
                 sublinks=[{'title':'One','url':'https://example.com/?tab=one'},{'title':'Two','url':'https://example.com/?tab=two'}])
    resource = data['objectives'][0]['resources'][-1]
    first, second = [r['id'] for r in resource['sublinks']]
    apply(monorepo, oid, 'asset-star', resource_id=resource['id'], sub_link_id=first, starred=True)
    apply(monorepo, oid, 'asset-bucket', resource_id=resource['id'], sub_link_id=second, bucket='archive')
    data = apply(monorepo, oid, 'link-remove-sublink', resource_id=resource['id'], sub_link_id=first)
    assert data['objectives'][0]['shared_assets'] == []
    assert data['objectives'][0]['archived_assets'][0]['sub_link_id'] == second
    data = apply(monorepo, oid, 'remove-resource', resource_id=resource['id'])
    assert data['objectives'][0]['archived_assets'] == []
