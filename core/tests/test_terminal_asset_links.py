"""Asset navigation is independent of terminal ownership and launch metadata."""
from copy import deepcopy

import pytest

from lab import objectives
from core.routes import term


@pytest.mark.parametrize('origin', ['task', 'objective', 'workspace', 'child', 'folder'])
def test_link_replace_and_unlink_preserve_terminal_origin(client, monorepo, seed_workspace, origin):
    folder = seed_workspace()
    def action(**fields):
        result = client.post('/api/objectives', json={'workspace_id':'demo', 'action':fields})
        assert result.status_code == 200, result.text
        return result.json()
    owner = action(type='create', name='Owner')['objectives'][0]['id']
    task = action(type='task', objective_id=owner, title='Primary')['objectives'][0]['tasks'][0]['id']
    other = action(type='create', name='Asset Objective')['objectives'][-1]['id']
    data = action(type='resource', objective_id=other, kind='link', title='GitHub', url='https://github.com/example/repo',
                  sublinks=[{'title':'Issue', 'url':'https://github.com/example/repo/issues/1'}])
    resource = data['objectives'][-1]['resources'][0]
    term._upsert_workspace_session(monorepo, 'demo', {'name':'shell', 'kind':'terminal', 'cwd':str(folder), 'label':'Keep me'})
    session = term._get_workspace_sessions(monorepo, 'demo')[0]
    target = {'main':'workflow'} if origin == 'workspace' else {'objective_id':owner, **(
        {'task_id':task} if origin == 'task' else {'main':'objective'} if origin == 'objective'
        else {'folder':{'root':str(folder),'path':'.'}} if origin == 'folder' else {'view':'tasks'})}
    before = deepcopy(action(type='terminal', session_id=session['session_id'], **target)['terminal_links'][session['session_id']])
    base = {'type':'terminal-asset', 'session_id':session['session_id'], 'objective_id':other}
    linked = action(**base, resource_id=resource['id'], sub_link_id=resource['sublinks'][0]['id'])['terminal_links'][session['session_id']]
    assert {k:v for k,v in linked.items() if k != 'asset'} == before
    assert linked['asset'] == {'objective_id':other, 'resource_id':resource['id'], 'sub_link_id':resource['sublinks'][0]['id']}
    notebook = action(type='resource', objective_id=other, kind='notebook', title='Analysis')['objectives'][-1]['resources'][-1]
    linked = action(**base, resource_id=notebook['id'])['terminal_links'][session['session_id']]
    assert linked == {**before, 'asset':{'objective_id':other, 'resource_id':notebook['id']}}
    # Reasserting origin (including an automation retry) keeps the asset binding.
    assert action(type='terminal', session_id=session['session_id'], **target)['terminal_links'][session['session_id']] == linked
    assert action(type='terminal-asset', session_id=session['session_id'], unlink=True)['terminal_links'][session['session_id']] == before
    assert action(type='terminal-asset', session_id=session['session_id'], unlink=True)['terminal_links'][session['session_id']] == before
    assert term._get_workspace_sessions(monorepo, 'demo') == [session]


def test_asset_link_validation_and_file_scope(monorepo, seed_workspace):
    folder = seed_workspace()
    data = objectives.mutate(monorepo, 'demo', {'type':'create', 'name':'Project'})
    oid = data['objectives'][0]['id']
    file = folder/'sample.ipynb';file.write_text('{}')
    base = {'type':'terminal-asset', 'session_id':'shell', 'objective_id':oid}
    for patch in [{}, {'resource_id':'missing'}, {'file':{'root':str(folder), 'path':'../missing'}},
                  {'file':{'root':'/', 'path':'etc/hosts'}}, {'file':'invalid'},
                  {'folder':{'root':str(folder), 'path':'.'}, 'task_id':'other'}]:
        with pytest.raises(ValueError):
            objectives.mutate(monorepo, 'demo', {**base, **patch})
        assert objectives.load(monorepo, 'demo')['terminal_links'] == {}
    data = objectives.mutate(monorepo, 'demo', {**base, 'file':{'root':str(folder), 'path':file.name}})
    assert data['terminal_links']['shell'] == {'view':'workflow', 'asset':{
        'objective_id':oid, 'file':{'root':str(folder), 'path':file.name}}}


def test_asset_api_rejects_unowned_session(client, seed_workspace):
    seed_workspace()
    response = client.post('/api/objectives', json={'workspace_id':'demo', 'action':{
        'type':'terminal-asset', 'session_id':'foreign', 'unlink':True}})
    assert response.status_code == 400
