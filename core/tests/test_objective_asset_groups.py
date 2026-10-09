"""Client grouping changes presentation, retaining content and assignments."""
from copy import deepcopy
import json

import pytest
from lab import objectives, objective_asset_groups


@pytest.fixture()
def grouped_workspace(monorepo, seed_workspace):
    folder = seed_workspace()
    oid = objectives.mutate(monorepo, 'demo', {'type':'create', 'name':'Grouped references'})['objectives'][0]['id']

    def act(operation, **fields):
        return objectives.mutate(monorepo, 'demo', {'type':operation, 'objective_id':oid, **fields})['objectives'][0]

    task = act('task', title='Review sections')['tasks'][0]
    refs = []
    for name in ('Overview', 'Evidence', 'Decisions'):
        resource = act('resource', kind='link', title=name,
                       url='https://docs.google.com/document/d/example/edit#heading='+name.lower())['resources'][-1]
        refs.append({'resource_id':resource['id']})
        act('asset-star', **refs[-1], starred=True)
        act('task-asset', task_id=task['id'], **refs[-1])
    act('terminal', session_id='section-shell', **refs[0])
    return folder, oid, task, refs, act


def test_group_order_and_ungroup_preserve_originals(monorepo, grouped_workspace):
    folder, oid, task, refs, act = grouped_workspace
    original = objectives.load(monorepo, 'demo')
    before = deepcopy(objectives.payload(monorepo, 'demo')['objectives'][0])
    assert 'asset_groups' not in before  # Matching document URLs never infer groups.
    files = {p:p.read_bytes() for p in folder.rglob('*.md')}
    grouped = act('asset-group-create', title='Google Doc sections', **refs[0])
    gid = grouped['asset_groups'][0]['id']
    grouped = act('asset-group-member', group_id=gid, **refs[1])
    assert grouped['asset_groups'][0]['assets'] == refs[:2]
    assert grouped['asset_order'] == [{'group_id':gid}, refs[2]]
    grouped = act('asset-order', item=refs[1], relative=refs[0], position='before')
    assert grouped['asset_groups'][0]['assets'] == [refs[1], refs[0]]
    # Saving the same group again must preserve its selected child position.
    grouped = act('asset-group-member', group_id=gid, **refs[1])
    assert grouped['asset_groups'][0]['assets'] == [refs[1], refs[0]]
    grouped = act('asset-order', item={'group_id':gid}, relative=refs[2], position='after')
    assert grouped['asset_order'] == [refs[2], {'group_id':gid}]
    grouped = act('asset-group-rename', group_id=gid, title='Document sections')
    assert grouped['asset_groups'][0]['title'] == 'Document sections'
    persisted = objectives.load(monorepo, 'demo')['objectives'][0]
    assert persisted['asset_groups'] == grouped['asset_groups']
    assert persisted['asset_order'] == grouped['asset_order']
    for field in ('resources', 'tasks', 'shared_assets', 'archived_assets', 'worktrees'):
        assert grouped[field] == before[field]
    assert objectives.load(monorepo, 'demo')['terminal_links'] == original['terminal_links']
    released = act('asset-group-ungroup', group_id=gid)
    assert released['asset_groups'] == []
    assert released['asset_order'] == [refs[2], refs[1], refs[0]]
    assert released['resources'] == before['resources'] and released['tasks'] == before['tasks']
    assert all(p.read_bytes() == content for p, content in files.items())


def test_membership_moves_are_flat_and_do_not_reassign(monorepo, grouped_workspace):
    _, _, _, refs, act = grouped_workspace
    a = act('asset-group-create', title='First', **refs[0])['asset_groups'][0]['id']
    grouped = act('asset-group-create', title='Second', **refs[1])
    b = grouped['asset_groups'][1]['id']
    tasks = deepcopy(grouped['tasks'])
    grouped = act('asset-group-member', group_id=b, **refs[0])
    assert grouped['asset_groups'][0]['assets'] == []
    assert grouped['asset_groups'][1]['assets'] == [refs[1], refs[0]]
    grouped = act('asset-group-member', group_id=None, **refs[1])
    assert grouped['asset_groups'][1]['assets'] == [refs[0]]
    assert grouped['asset_order'][-1] == refs[1]
    assert grouped['tasks'] == tasks
    # Empty named groups remain available for the client to reuse.
    grouped = act('asset-group-member', group_id=a, **refs[2])
    assert grouped['asset_groups'][0]['assets'] == [refs[2]]


def test_invalid_group_changes_are_atomic(client, monorepo, grouped_workspace):
    _, oid, task, refs, act = grouped_workspace
    gid = act('asset-group-create', title='Sections', **refs[0])['asset_groups'][0]['id']
    for fields in [
        {'type':'asset-group-create', 'title':' ', **refs[1]},
        {'type':'asset-group-create', 'title':'Nested', 'group_id':gid},
        {'type':'asset-group-member', 'group_id':'missing', **refs[1]},
        {'type':'asset-group-member', 'group_id':gid, 'resource_id':'missing'},
        {'type':'asset-group-member', 'group_id':gid, 'resource_id':task['document_id'], 'tab_id':task['tab_id']},
        {'type':'asset-group-create', 'title':'Import', 'reference':{'kind':'link','url':'https://example.com/'}},
        {'type':'asset-order', 'item':refs[0], 'relative':refs[1], 'position':'before'},
        {'type':'asset-order', 'item':{'group_id':gid}, 'relative':refs[0], 'position':'before'},
    ]:
        before = objectives.load(monorepo, 'demo')
        response = client.post('/api/objectives', json={'workspace_id':'demo', 'expected':before['revision'],
                                                       'action':{'objective_id':oid, **fields}})
        assert response.status_code == 400, response.text
        assert objectives.load(monorepo, 'demo') == before


def test_removed_and_trashed_references_prune_groups(monorepo, grouped_workspace):
    _, _, _, refs, act = grouped_workspace
    gid = act('asset-group-create', title='Sections', **refs[0])['asset_groups'][0]['id']
    act('asset-group-member', group_id=gid, **refs[1])
    after = act('remove-resource', **refs[0])
    assert after['asset_groups'][0]['assets'] == [refs[1]]
    after = act('asset-trash', confirmed=True, **refs[1])
    assert after['asset_groups'][0]['assets'] == []
    assert all(a.get('resource_id') not in {r['resource_id'] for r in refs[:2]} for a in after['asset_order'])


def test_grouped_sublinks_and_folders_keep_their_exact_targets(monorepo, grouped_workspace):
    folder, _, _, _, act = grouped_workspace
    source = folder/'reference.md'
    source.write_text('Original content\n')
    file = act('resource', kind='file', path=source.name, title='Original reference')['resources'][-1]
    link = act('resource', kind='link', title='Document', url='https://docs.google.com/document/d/example/edit',
               sublinks=[{'title':'Evidence', 'url':'https://docs.google.com/document/d/example/edit#heading=evidence'}])['resources'][-1]
    sublink = {'resource_id':link['id'], 'sub_link_id':link['sublinks'][0]['id']}
    grouped = act('asset-group-create', title='References', **sublink)
    gid = grouped['asset_groups'][0]['id']
    act('asset-group-member', group_id=gid, resource_id=file['id'])
    # Folder registration uses the existing asset operations, then groups that reference.
    act('asset-star', folder={'root':str(folder), 'path':'.'}, starred=True)
    grouped = act('asset-group-member', group_id=gid, folder={'root':str(folder), 'path':'.'})
    assert grouped['asset_groups'][0]['assets'] == [sublink, {'resource_id':file['id']}, {'folder':{'root':str(folder), 'path':'.'}}]
    assert source.read_text() == 'Original content\n'
    grouped = act('link-remove-sublink', **sublink)
    assert grouped['asset_groups'][0]['assets'] == [{'resource_id':file['id']}, {'folder':{'root':str(folder), 'path':'.'}}]


def test_all_group_actions_are_available_through_lab_cli(grouped_workspace, tmp_path):
    from click.testing import CliRunner
    from lab.cli import main

    _, oid, _, refs, _ = grouped_workspace
    runner = CliRunner()
    action_file = tmp_path/'group-action.json'

    def read():
        result = runner.invoke(main, ['objective', 'ls', '--workspace', 'demo'])
        assert result.exit_code == 0, result.output
        return json.loads(result.output)

    original = read()['objectives'][0]

    def apply(operation, **fields):
        before = read()
        action_file.write_text(json.dumps({'type':operation, 'objective_id':oid, **fields}))
        result = runner.invoke(main, ['objective', 'apply', '--workspace', 'demo',
                                     '--file', str(action_file), '--expected', before['revision']])
        assert result.exit_code == 0, result.output
        return json.loads(result.output)['objectives'][0]

    grouped = apply('asset-group-create', title='Document sections', **refs[0])
    gid = grouped['asset_groups'][0]['id']
    grouped = apply('asset-group-member', group_id=gid, **refs[1])
    assert grouped['asset_groups'][0]['assets'] == refs[:2]
    grouped = apply('asset-order', item=refs[1], relative=refs[0], position='before')
    assert grouped['asset_groups'][0]['assets'] == [refs[1], refs[0]]
    grouped = apply('asset-order', item={'group_id':gid}, relative=refs[2], position='after')
    assert grouped['asset_order'] == [refs[2], {'group_id':gid}]
    grouped = apply('asset-group-rename', group_id=gid, title='Renamed sections')
    assert grouped['asset_groups'][0]['title'] == 'Renamed sections'
    grouped = apply('asset-group-member', group_id=None, **refs[1])
    assert grouped['asset_groups'][0]['assets'] == [refs[0]]
    grouped = apply('asset-group-ungroup', group_id=gid)
    assert grouped['asset_groups'] == []
    persisted = read()['objectives'][0]
    assert persisted['asset_order'] == [refs[2], refs[0], refs[1]]
    for field in ('resources', 'tasks', 'shared_assets'):
        assert persisted[field] == original[field]
    help_result = runner.invoke(main, ['objective', 'apply', '--help'])
    assert help_result.exit_code == 0
    for action in ('asset-group-create', 'asset-group-member', 'asset-group-rename', 'asset-group-ungroup', 'asset-order'):
        assert action in help_result.output


@pytest.mark.parametrize('groups, order', [
    ([{'id':'a','title':'Group','assets':[{'group_id':'b'}]}], []),
    ([{'id':'a','title':'Group','assets':[{'resource_id':'x'}]}, {'id':'b','title':'Other','assets':[{'resource_id':'x'}]}], []),
    ([{'id':'a','title':'Group','assets':[{'resource_id':'x'}]}], [{'resource_id':'x'}]),
    ([], [{'group_id':[]}]),
])
def test_invalid_persisted_group_layout_is_rejected(groups, order):
    with pytest.raises(ValueError):
        objective_asset_groups.validate({'asset_groups':groups, 'asset_order':order})
