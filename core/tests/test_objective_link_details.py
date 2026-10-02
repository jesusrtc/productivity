"""External link details retain their identity, scopes and nested targets."""
from copy import deepcopy

import pytest
from lab import objectives


@pytest.fixture()
def links(monorepo, seed_workspace):
    folder = seed_workspace()
    data = objectives.mutate(monorepo, 'demo', {'type':'create', 'name':'Links'})
    oid = data['objectives'][0]['id']
    data = objectives.mutate(monorepo, 'demo', {'type':'resource', 'objective_id':oid,
        'kind':'link', 'title':'Doc', 'url':'https://docs.google.com/document/d/example/edit',
        'tldr':'Incident context', 'metadata':{'Owner':'Operations', 'Tags':['review', 'incident']},
        'sublinks':[{'title':'Overview', 'url':'https://docs.google.com/document/d/example/edit?tab=overview'},
                    {'title':'Investigation', 'url':'https://docs.google.com/document/d/example/edit?tab=investigation'}]})
    return folder, oid, data['objectives'][0]['resources'][0]


def change(root, oid, rid, operation='link-update', **fields):
    return objectives.mutate(root, 'demo', {'type':operation, 'objective_id':oid, 'resource_id':rid, **fields})


def test_link_edits_keep_scope_children_and_terminal_associations(monorepo, links):
    folder, oid, link = links
    tree = objectives.mutate(monorepo, 'demo', {'type':'worktree', 'objective_id':oid, 'path':str(folder)})['objectives'][0]['worktrees'][0]
    change(monorepo, oid, link['id'], 'scope', worktree=tree['id'])
    change(monorepo, oid, link['id'], 'terminal', session_id='saved-terminal', sub_link_id=link['sublinks'][0]['id'])
    data = change(monorepo, oid, link['id'], title='Updated Doc', url='https://docs.google.com/document/d/example/edit#heading', tldr='Updated summary', metadata={'Owner':'Engineering'})
    updated = data['objectives'][0]['resources'][0]
    assert updated['id'] == link['id'] and updated['kind'] == 'link' and updated['worktree'] == tree['id']
    assert updated['sublinks'] == link['sublinks']
    assert updated['tldr'] == 'Updated summary' and updated['metadata'] == {'Owner':'Engineering'}
    assert data['terminal_links']['saved-terminal']['sub_link_id'] == link['sublinks'][0]['id']
    child = link['sublinks'][0]
    data = change(monorepo, oid, link['id'], sub_link_id=child['id'], title='Edited overview', tldr='Tab summary')
    children = data['objectives'][0]['resources'][0]['sublinks']
    assert children[0]['id'] == child['id'] and children[0]['tldr'] == 'Tab summary'
    assert children[1] == link['sublinks'][1]
    data = change(monorepo, oid, link['id'], 'link-sublink', parent_id=child['id'], title='Evidence', url='https://example.com/evidence')
    nested = data['objectives'][0]['resources'][0]['sublinks'][0]['sublinks'][0]
    change(monorepo, oid, link['id'], 'terminal', session_id='nested-terminal', sub_link_id=nested['id'])
    data = change(monorepo, oid, link['id'], 'link-remove-sublink', sub_link_id=child['id'])
    assert data['objectives'][0]['resources'][0]['sublinks'] == [link['sublinks'][1]]
    assert all(row['resource_id'] == link['id'] and 'sub_link_id' not in row for row in data['terminal_links'].values())
    change(monorepo, oid, link['id'], 'terminal', session_id='replacement-terminal', sub_link_id=link['sublinks'][1]['id'])
    data = change(monorepo, oid, link['id'], sublinks=[])
    assert data['terminal_links']['replacement-terminal']['resource_id'] == link['id']
    assert 'sub_link_id' not in data['terminal_links']['replacement-terminal']


def test_invalid_link_details_are_atomic(monorepo, links):
    _, oid, link = links
    invalid = [{'url':'javascript:alert(1)'}, {'url':'https://example.com/\nfoo'}, {'title':''},
               {'tldr':None}, {'tldr':'x'*8193}, {'metadata':[]}, {'metadata':{'':1}},
               {'metadata':{'bad':float('nan')}}, {'metadata':{'large':'x'*16385}},
               {'sub_link_id':'missing', 'title':'Wrong child'},
               {'sublinks':[link['sublinks'][0], link['sublinks'][0]]}]
    nested = {'title':'Nested', 'url':'https://example.com/'}
    for _ in range(5):
        nested = {**deepcopy(nested), 'sublinks':[deepcopy(nested)]}
    invalid.append({'sublinks':[nested]})
    for fields in invalid:
        original = objectives.registry(monorepo, 'demo').read_bytes()
        with pytest.raises(ValueError):
            change(monorepo, oid, link['id'], **fields)
        assert objectives.registry(monorepo, 'demo').read_bytes() == original
    with pytest.raises(ValueError, match='Sublink not found'):
        change(monorepo, oid, link['id'], 'terminal', session_id='terminal', sub_link_id='missing')


def test_old_links_need_no_migration_and_stale_metadata_is_rejected(monorepo, seed_workspace):
    seed_workspace()
    oid = objectives.mutate(monorepo, 'demo', {'type':'create', 'name':'Legacy'})['objectives'][0]['id']
    data = objectives.mutate(monorepo, 'demo', {'type':'resource', 'objective_id':oid, 'kind':'link', 'title':'Legacy link', 'url':'https://example.com/'})
    link = data['objectives'][0]['resources'][0]
    original = objectives.registry(monorepo, 'demo').read_bytes()
    assert objectives.payload(monorepo, 'demo')['objectives'][0]['resources'][0] == link
    assert objectives.registry(monorepo, 'demo').read_bytes() == original
    assert not any(field in link for field in ['tldr', 'metadata', 'sublinks'])
    change(monorepo, oid, link['id'], tldr='Summary')
    with pytest.raises(ValueError, match='changed elsewhere'):
        objectives.mutate(monorepo, 'demo', {'type':'link-update', 'objective_id':oid, 'resource_id':link['id'], 'tldr':'Stale'}, expected=data['revision'])
