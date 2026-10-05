"""Reviewable suggestions, atomic assignments and nondestructive asset cleanup."""
import pytest
from lab import objectives


@pytest.fixture
def organization(monorepo, seed_workspace):
    folder = seed_workspace()
    oid = objectives.mutate(monorepo, 'demo', {'type':'create', 'name':'Research'})['objectives'][0]['id']
    for title in ('Measure', 'Review'):
        objectives.mutate(monorepo, 'demo', {'type':'task', 'objective_id':oid, 'title':title})
    data = objectives.mutate(monorepo, 'demo', {'type':'resource', 'objective_id':oid,
                            'kind':'document', 'title':'Measurements', 'body':'Original evidence'})
    owner = data['objectives'][0]
    return folder, oid, owner['tasks'], owner['resources'][-1]


def change(root, oid, operation, **fields):
    return objectives.mutate(root, 'demo', {'type':operation, 'objective_id':oid, **fields})


def propose(root, oid, resource, task):
    return change(root, oid, 'suggest-assignment', resource_id=resource['id'],
                  destination={'bucket':'task', 'task_id':task['id']}, reason='Contains the measurements needed by this task.')


def test_suggestions_only_add_review_records_and_rejected_pairs_stay_rejected(monorepo, organization):
    folder, oid, tasks, resource = organization
    original = (folder/resource['path']).read_bytes()
    before = objectives.load(monorepo, 'demo')['objectives'][0]
    propose(monorepo, oid, resource, tasks[0])
    owner = objectives.load(monorepo, 'demo')['objectives'][0]
    suggestion = owner.pop('assignment_suggestions')[0]
    assert owner == before
    assert suggestion['status'] == 'pending' and suggestion['destination']['objective_id'] == oid
    assert (folder/resource['path']).read_bytes() == original
    data = propose(monorepo, oid, resource, tasks[0])
    assert len(data['objectives'][0]['assignment_suggestions']) == 1
    data = change(monorepo, oid, 'reject-assignment', suggestion_id=suggestion['id'])
    assert data['objectives'][0]['assignment_suggestions'][0]['status'] == 'rejected'
    data = propose(monorepo, oid, resource, tasks[0])
    assert len(data['objectives'][0]['assignment_suggestions']) == 1
    assert data['objectives'][0]['tasks'] == before['tasks']
    data = propose(monorepo, oid, resource, tasks[1])
    assert len(data['objectives'][0]['assignment_suggestions']) == 2


def test_accept_and_manual_assignment_replace_membership_atomically(monorepo, organization):
    _, oid, tasks, resource = organization
    data = propose(monorepo, oid, resource, tasks[0])
    suggestion = data['objectives'][0]['assignment_suggestions'][0]
    owner = change(monorepo, oid, 'accept-assignment', suggestion_id=suggestion['id'])['objectives'][0]
    assert owner['tasks'][0]['assets'][0]['resource_id'] == resource['id']
    assert owner['assignment_suggestions'][0]['status'] == 'accepted'
    with pytest.raises(ValueError, match='no longer pending'):
        change(monorepo, oid, 'accept-assignment', suggestion_id=suggestion['id'])
    owner = change(monorepo, oid, 'asset-assign', resource_id=resource['id'],
                   destination={'bucket':'task', 'task_id':tasks[1]['id']})['objectives'][0]
    assert owner['tasks'][0]['assets'] == []
    assert owner['tasks'][1]['assets'][0]['resource_id'] == resource['id']
    owner = change(monorepo, oid, 'asset-assign', resource_id=resource['id'],
                   destination={'bucket':'objective'})['objectives'][0]
    assert owner['tasks'][1]['assets'] == [] and owner['shared_assets'][0]['resource_id'] == resource['id']


@pytest.mark.parametrize('extra', [
    {'resource_id':'missing'},
    {'destination':{'bucket':'task', 'task_id':'missing'}},
    {'destination':{'bucket':'archive'}},
    {'destination':{'bucket':'objective', 'objective_id':'missing'}},
    {'reason':''},
    {'reference':{'kind':'link', 'title':'New', 'url':'https://example.com/new'}},
])
def test_invalid_proposals_leave_the_entire_registry_unchanged(monorepo, organization, extra):
    _, oid, tasks, resource = organization
    before = objectives.load(monorepo, 'demo')
    action = {'type':'suggest-assignment', 'objective_id':oid, 'resource_id':resource['id'],
              'destination':{'bucket':'task', 'task_id':tasks[0]['id']}, 'reason':'Relevant evidence', **extra}
    with pytest.raises(ValueError):
        objectives.mutate(monorepo, 'demo', action)
    assert objectives.load(monorepo, 'demo') == before


def test_archive_and_task_specifications_are_protected(monorepo, organization):
    _, oid, tasks, resource = organization
    data = propose(monorepo, oid, resource, tasks[0])
    suggestion = data['objectives'][0]['assignment_suggestions'][0]
    change(monorepo, oid, 'asset-bucket', resource_id=resource['id'], bucket='archive')
    with pytest.raises(ValueError, match='archived asset'):
        propose(monorepo, oid, resource, tasks[0])
    with pytest.raises(ValueError, match='archived asset'):
        change(monorepo, oid, 'accept-assignment', suggestion_id=suggestion['id'])
    for operation in ('suggest-assignment', 'asset-assign', 'asset-trash'):
        with pytest.raises(ValueError, match='Task details'):
            change(monorepo, oid, operation, resource_id=tasks[0]['document_id'],
                   tab_id=tasks[0]['tab_id'], confirmed=True,
                   destination={'bucket':'task', 'task_id':tasks[1]['id']}, reason='Bad idea')


def test_cross_objective_accept_preserves_original_owned_content(monorepo, organization):
    folder, oid, _, resource = organization
    original = (folder/resource['path']).read_bytes()
    other = objectives.mutate(monorepo, 'demo', {'type':'create', 'name':'Reporting'})['objectives'][-1]['id']
    data = change(monorepo, oid, 'suggest-assignment', resource_id=resource['id'],
                  destination={'bucket':'objective', 'objective_id':other}, reason='Reports this outcome')
    assert data['objectives'][0]['resources'][-1]['id'] == resource['id']
    assert data['objectives'][1]['resources'] == []
    sid = data['objectives'][0]['assignment_suggestions'][0]['id']
    data = change(monorepo, oid, 'accept-assignment', suggestion_id=sid)
    assert not any(r['id'] == resource['id'] for r in data['objectives'][0]['resources'])
    moved = data['objectives'][1]['resources'][0]
    assert moved['kind'] == 'file' and moved['file_root'] == str(folder)
    assert moved['path'] == resource['path']
    assert data['objectives'][1]['shared_assets'][0]['resource_id'] == moved['id']
    assert (folder/resource['path']).read_bytes() == original


def test_worktree_proposal_does_not_move_until_accepted(monorepo, organization, tmp_path):
    _, oid, _, _ = organization
    checkout = tmp_path/'checkout';checkout.mkdir()
    change(monorepo, oid, 'worktree', path=str(checkout))
    other = objectives.mutate(monorepo, 'demo', {'type':'create', 'name':'Other'})['objectives'][-1]['id']
    data = change(monorepo, oid, 'suggest-assignment', folder={'root':str(checkout), 'path':'.'},
                  destination={'bucket':'objective', 'objective_id':other}, reason='Checkout for this outcome')
    assert len(data['objectives'][0]['worktrees']) == 1 and not data['objectives'][1]['worktrees']
    data = change(monorepo, oid, 'accept-assignment', suggestion_id=data['objectives'][0]['assignment_suggestions'][0]['id'])
    assert not data['objectives'][0]['worktrees'] and len(data['objectives'][1]['worktrees']) == 1
    assert data['objectives'][1]['shared_assets'][0]['folder']['root'] == str(checkout)


def test_trash_requires_confirmation_and_removes_only_the_registration(monorepo, organization):
    folder, oid, tasks, resource = organization
    original = (folder/resource['path']).read_bytes()
    change(monorepo, oid, 'task-asset', resource_id=resource['id'], task_id=tasks[0]['id'])
    propose(monorepo, oid, resource, tasks[1])
    before = objectives.load(monorepo, 'demo')
    with pytest.raises(ValueError, match='Confirm'):
        change(monorepo, oid, 'asset-trash', resource_id=resource['id'])
    assert objectives.load(monorepo, 'demo') == before
    data = change(monorepo, oid, 'asset-trash', resource_id=resource['id'], confirmed=True)
    assert not any(r['id'] == resource['id'] for r in data['objectives'][0]['resources'])
    assert not data['objectives'][0]['tasks'][0]['assets']
    assert not data['objectives'][0]['assignment_suggestions']
    assert (folder/resource['path']).read_bytes() == original


def test_rejected_stale_api_request_cannot_commit_an_assignment(client, monorepo, organization):
    _, oid, tasks, resource = organization
    data = propose(monorepo, oid, resource, tasks[0])
    sid = data['objectives'][0]['assignment_suggestions'][0]['id']
    change(monorepo, oid, 'settings', name='Changed elsewhere')
    response = client.post('/api/objectives', json={'workspace_id':'demo', 'expected':data['revision'],
                           'action':{'type':'accept-assignment', 'objective_id':oid, 'suggestion_id':sid}})
    assert response.status_code == 409
    current = objectives.load(monorepo, 'demo')['objectives'][0]
    assert not current['tasks'][0].get('assets') and current['assignment_suggestions'][0]['status'] == 'pending'


def test_unregistered_folder_is_not_silently_added_by_a_proposal(monorepo, organization):
    folder, oid, tasks, _ = organization
    (folder/'unused').mkdir()
    before = objectives.load(monorepo, 'demo')
    with pytest.raises(ValueError, match='Register the folder'):
        change(monorepo, oid, 'suggest-assignment', folder={'root':str(folder), 'path':'unused'},
               destination={'bucket':'task', 'task_id':tasks[0]['id']}, reason='Maybe useful')
    assert objectives.load(monorepo, 'demo') == before


def test_trashing_a_subtab_preserves_its_document_and_other_assignments(monorepo, organization):
    folder, oid, tasks, resource = organization
    data = change(monorepo, oid, 'subtab', resource_id=resource['id'], title='Optional appendix', body='Keep the source')
    rid = resource['id']
    tab = next(r for r in data['objectives'][0]['resources'] if r['id'] == rid)['content']['tabs'][0]['id']
    original = (folder/resource['path']).read_bytes()
    change(monorepo, oid, 'task-asset', resource_id=rid, task_id=tasks[0]['id'])
    change(monorepo, oid, 'task-asset', resource_id=rid, tab_id=tab, task_id=tasks[1]['id'])
    owner = change(monorepo, oid, 'asset-trash', resource_id=rid, tab_id=tab, confirmed=True)['objectives'][0]
    assert any(r['id'] == rid for r in owner['resources'])
    assert owner['tasks'][0]['assets'][0]['resource_id'] == rid and not owner['tasks'][1]['assets']
    assert owner['trashed_assets'][0]['tab_id'] == tab
    assert (folder/resource['path']).read_bytes() == original
    with pytest.raises(ValueError, match='removed'):
        change(monorepo, oid, 'suggest-assignment', resource_id=rid, tab_id=tab,
               destination={'bucket':'task', 'task_id':tasks[0]['id']}, reason='Already removed')


def test_cli_can_propose_with_a_revision_without_assigning(monorepo, organization, tmp_path):
    import json
    from click.testing import CliRunner
    from lab.cli import main
    _, oid, tasks, resource = organization
    data = objectives.load(monorepo, 'demo')
    action = tmp_path/'suggestion.json'
    action.write_text(json.dumps({'type':'suggest-assignment', 'objective_id':oid, 'resource_id':resource['id'],
                      'destination':{'bucket':'task', 'task_id':tasks[0]['id']}, 'reason':'Evidence for this task'}))
    runner = CliRunner()
    args = ['objective', 'apply', '--workspace', 'demo', '--expected', data['revision'], '--file', str(action)]
    result = runner.invoke(main, args)
    assert result.exit_code == 0, result.output
    owner = json.loads(result.output)['objectives'][0]
    assert owner['assignment_suggestions'][0]['status'] == 'pending' and not owner['tasks'][0].get('assets')
    assert runner.invoke(main, args).exit_code != 0
    guide = runner.invoke(main, ['context', 'objectives'])
    assert guide.exit_code == 0 and 'Never call `accept-assignment`' in guide.output
