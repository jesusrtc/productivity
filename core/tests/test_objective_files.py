"""Objective-folder discovery, external edits and lossless legacy conversion."""
from copy import deepcopy
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import pytest
from click.testing import CliRunner
from lab import assistant_documents, objective_store, objectives, storage
from lab.commands.objective import objective_group


def snapshot(folder):
    return {str(path.relative_to(folder)): path.read_bytes() for path in folder.rglob('*')
            if path.is_file() and path.name != 'objectives.lock'}


def native(folder, name='phone-recovery', oid='phone', **fields):
    target = folder / 'objectives' / name / '.objective.json'
    storage.write_json(target, {'version': 1, 'id': oid, 'name': 'Phone recovery', **fields})
    return target


@pytest.fixture()
def legacy(monorepo, seed_workspace):
    folder = seed_workspace()
    o = {'id': 'stable-objective', 'name': 'Phone', 'purpose': 'Restore verification',
         'worktrees': [], 'tasks': [], 'resources': [], 'custom': {'keep': [1, 2]}}
    owned = folder / 'objectives' / o['id']
    owned.mkdir(parents=True)
    doc = owned / 'Tasks.md'
    assistant_documents_data = assistant_documents.pack(
        {'schema': 2, 'id': 'spec', 'type': 'note', 'title': 'Tasks'}, '# Tasks',
        [({'schema': 2, 'id': 'parent-tab', 'type': 'note', 'title': 'Verify'}, 'Parent evidence'),
         ({'schema': 2, 'id': 'child-tab', 'type': 'note', 'title': 'Edge',
           'parent': {'id': 'parent-tab', 'type': 'note'}}, 'Child evidence')])
    doc.write_bytes(assistant_documents_data)
    o['resources'] = [
        {'id': 'spec', 'kind': 'document', 'title': 'Tasks.md', 'path': doc.relative_to(folder).as_posix()},
        {'id': 'slack', 'kind': 'link', 'title': 'Discussion', 'url': 'https://example.slack.com/archives/team',
         'tldr': 'Evidence', 'metadata': {'owner': 'Team'},
         'sublinks': [{'id': 'thread', 'title': 'Thread', 'url': 'https://example.slack.com/archives/team/thread'}]},
        {'id': 'assistant', 'kind': 'assistant', 'title': 'Original', 'assistant_root': '/original/assistant',
         'document_id': 'original-document', 'tab_id': 'original-tab'}]
    child = {'id': 'child', 'title': 'Edge', 'done': False, 'children': [], 'document_id': 'spec', 'tab_id': 'child-tab'}
    o['tasks'] = [{'id': 'parent', 'title': 'Verify', 'done': False, 'children': [child],
                   'document_id': 'spec', 'tab_id': 'parent-tab',
                   'assets': [{'id': 'asset', 'resource_id': 'slack', 'sub_link_id': 'thread'}], 'icon_asset_id': 'asset'}]
    o['shared_assets'] = [{'id': 'shared', 'resource_id': 'slack'}]
    o['archived_assets'] = [{'id': 'archived', 'resource_id': 'assistant'}]
    notebook = owned / 'Volume.ipynb'
    notebook.write_text('{"nbformat":4,"nbformat_minor":5,"metadata":{},"cells":[]}\n')
    o['resources'].append({'id': 'notebook', 'kind': 'notebook', 'title': notebook.name,
                           'path': notebook.relative_to(folder).as_posix()})
    checkout = monorepo / 'worktree'
    checkout.mkdir()
    o['worktrees'] = [{'id': 'tree', 'path': str(checkout), 'label': 'fix', 'repo': str(checkout), 'branch': 'fix', 'kind': 'worktree'}]
    o['tasks'][0]['assets'].append({'id': 'tree-asset', 'folder': {'root': str(checkout), 'path': '.'}})
    source = objective_store.legacy_file(folder)
    saved = {'version': 1, 'enabled': True, 'focused': [o['id']], 'objectives': [o],
             'terminal_links': {'terminal': {'objective_id': o['id'], 'task_id': 'child'}}, 'extension': 'keep'}
    storage.write_json(source, saved)
    return folder, source, o, doc


def test_native_files_are_discovered_without_a_registry_and_reads_do_not_write(monorepo, seed_workspace):
    folder = seed_workspace()
    target = native(folder, resources=[{'id': 'link', 'kind': 'link', 'title': 'Slack', 'url': 'https://slack.com'}])
    before = snapshot(folder)
    data = objectives.payload(monorepo, 'demo')
    o = data['objectives'][0]
    assert data['enabled'] and data['focused'] == ['phone']
    assert o['path'] == str(target.parent) and o['manifest_path'] == str(target)
    assert o['resources'][0]['url'] == 'https://slack.com'
    assert snapshot(folder) == before
    assert not objective_store.state_file(folder).exists()
    assert not objective_store.legacy_file(folder).exists()


def test_external_edits_and_folder_moves_are_authoritative_and_block_stale_writes(monorepo, seed_workspace):
    folder = seed_workspace()
    target = native(folder)
    before = objectives.load(monorepo, 'demo')
    value = storage.read_json(target)
    value['name'] = 'Edited outside Lab'
    value['resources'] = [{'id': 'doc', 'kind': 'document', 'title': 'Evidence.md', 'path': 'Evidence.md'}]
    storage.write_json(target, value)
    (target.parent / 'Evidence.md').write_bytes(assistant_documents.pack(
        {'schema': 2, 'id': 'doc', 'type': 'note', 'title': 'Evidence'}, '# Evidence', []))
    with pytest.raises(ValueError, match='changed elsewhere'):
        objectives.mutate(monorepo, 'demo', {'type': 'settings', 'objective_id': 'phone', 'name': 'Lost'}, before['revision'])
    moved = target.parent.with_name('new-folder-name')
    target.parent.rename(moved)
    data = objectives.payload(monorepo, 'demo')
    o = data['objectives'][0]
    assert o['id'] == 'phone' and o['name'] == 'Edited outside Lab' and o['path'] == str(moved)
    assert o['resources'][0]['content']['body'] == '# Evidence'
    data = objectives.mutate(monorepo, 'demo', {'type': 'resource', 'objective_id': 'phone', 'title': 'New document'})
    o = data['objectives'][0]
    assert (moved / 'New document.md').is_file()
    assert storage.read_json(moved / '.objective.json')['resources'][-1]['path'] == 'New document.md'
    assert not (folder / 'objectives' / 'phone').exists()


def test_focus_only_writes_ui_state_and_other_objectives_remain_untouched(monorepo, seed_workspace):
    folder = seed_workspace()
    first = native(folder, custom={'keep': True})
    second = native(folder, name='another', oid='another')
    originals = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in [first, second]}
    objectives.mutate(monorepo, 'demo', {'type': 'focus', 'objective_id': 'another', 'slot': 0})
    assert {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in originals} == originals
    objectives.mutate(monorepo, 'demo', {'type': 'resource', 'objective_id': 'phone', 'kind': 'link', 'title': 'Docs', 'url': 'https://docs.google.com/document/d/example'})
    assert (second.read_bytes(), second.stat().st_mtime_ns) == originals[second]
    saved = storage.read_json(first)
    assert saved['custom'] == {'keep': True} and saved['resources'][0]['kind'] == 'link'
    state = storage.read_json(objectives.registry(monorepo, 'demo'))
    assert 'objectives' not in state and 'resources' not in state and 'tasks' not in state
    assert state['focused'][0] == 'another'


def test_legacy_reads_and_preview_are_nonmutating_then_migration_is_lossless(monorepo, legacy):
    folder, source, original, doc = legacy
    before = snapshot(folder)
    old = objectives.load(monorepo, 'demo')
    assert old['objectives'][0]['manifest_path'] == str(source) + '#objective=' + original['id']
    preview = objectives.migrate(monorepo, 'demo')
    assert preview['migration_required'] and not preview['applied'] and snapshot(folder) == before
    report = objectives.migrate(monorepo, 'demo', apply=True)
    assert report['applied'] and not source.exists()
    assert Path(report['legacy_backup']).read_bytes() == before[str(source.relative_to(folder))]
    assert doc.read_bytes() == before[str(doc.relative_to(folder))]
    target = doc.parent / '.objective.json'
    saved = storage.read_json(target)
    expected = deepcopy(original)
    expected.update(version=1, asset_shelf=[])
    expected['resources'][0]['path'] = 'Tasks.md'
    expected['resources'][-1]['path'] = 'Volume.ipynb'
    assert saved == expected
    assert all((folder / name).read_bytes() == content for name, content in before.items()
               if name != str(source.relative_to(folder)))
    state = storage.read_json(objectives.registry(monorepo, 'demo'))
    assert state['terminal_links'] == old['terminal_links'] and state['extension'] == 'keep'
    new = objectives.load(monorepo, 'demo')
    assert new['objectives'][0]['tasks'] == old['objectives'][0]['tasks']
    assert new['objectives'][0]['resources'] == old['objectives'][0]['resources']
    after = snapshot(folder)
    assert not objectives.migrate(monorepo, 'demo', apply=True)['migration_required']
    assert snapshot(folder) == after
    # Removing a native file must not resurrect its backed-up legacy Objective.
    target.unlink()
    assert objectives.load(monorepo, 'demo')['objectives'] == []


def test_valid_legacy_mutations_migrate_but_invalid_ones_do_not(monorepo, legacy):
    folder, source, original, doc = legacy
    before = snapshot(folder)
    with pytest.raises(ValueError, match='full http'):
        objectives.mutate(monorepo, 'demo', {'type': 'resource', 'objective_id': original['id'], 'kind': 'link', 'title': 'Bad', 'url': 'javascript:bad'})
    assert snapshot(folder) == before
    data = objectives.mutate(monorepo, 'demo', {'type': 'link-update', 'objective_id': original['id'], 'resource_id': 'slack', 'tldr': 'Updated'})
    assert data['objectives'][0]['resources'][1]['tldr'] == 'Updated'
    assert not source.exists() and (doc.parent / '.objective.json').is_file()
    assert doc.read_bytes() == before[str(doc.relative_to(folder))]


def test_migration_keeps_preexisting_backups(monorepo, legacy):
    folder, source, original, doc = legacy
    backup = folder / '.lab' / 'objectives.legacy.json'
    backup.write_text('An older backup must stay untouched\n')
    old = backup.read_bytes()
    raw = source.read_bytes()
    report = objectives.migrate(monorepo, 'demo', apply=True)
    assert backup.read_bytes() == old
    assert report['legacy_backup'].endswith('objectives.legacy-1.json')
    assert Path(report['legacy_backup']).read_bytes() == raw


def test_interrupted_migration_can_be_retried_without_data_loss(monorepo, legacy, monkeypatch):
    folder, source, original, doc = legacy
    second = deepcopy(original)
    second.update(id='second', name='Second', resources=[], tasks=[])
    saved = storage.read_json(source)
    saved['objectives'].append(second)
    storage.write_json(source, saved)
    raw = source.read_bytes()
    real = storage.write_json
    def interrupt(path, value):
        if path == folder / 'objectives' / 'second' / '.objective.json':
            raise OSError('Interrupted conversion')
        real(path, value)
    monkeypatch.setattr(storage, 'write_json', interrupt)
    with pytest.raises(OSError, match='Interrupted'):
        objectives.migrate(monorepo, 'demo', apply=True)
    assert source.read_bytes() == raw and not objective_store.state_file(folder).exists()
    assert [o['id'] for o in objectives.load(monorepo, 'demo')['objectives']] == [original['id'], 'second']
    monkeypatch.setattr(storage, 'write_json', real)
    assert objectives.migrate(monorepo, 'demo', apply=True)['applied']
    assert (folder / '.lab' / 'objectives.legacy.json').read_bytes() == raw


@pytest.mark.parametrize('failure', ['malformed', 'duplicate', 'escape', 'symlink'])
def test_invalid_or_conflicting_manifests_never_get_overwritten(monorepo, seed_workspace, failure):
    folder = seed_workspace()
    target = native(folder)
    if failure == 'malformed':
        target.write_text('{unfinished')
    elif failure == 'duplicate':
        native(folder, name='duplicate')
    elif failure == 'escape':
        native(folder, resources=[{'id': 'doc', 'kind': 'document', 'title': 'Escape', 'path': '../../outside.md'}])
    else:
        outside = monorepo / 'outside.json'
        target.rename(outside)
        target.symlink_to(outside)
    before = snapshot(folder)
    with pytest.raises(ValueError):
        objectives.mutate(monorepo, 'demo', {'type': 'settings', 'objective_id': 'phone', 'name': 'Overwrite'})
    assert snapshot(folder) == before


def test_conflicting_native_file_blocks_legacy_migration_before_any_writes(monorepo, legacy):
    folder, source, original, doc = legacy
    native(folder, name=original['id'], oid=original['id'], name_extension='conflict')
    before = snapshot(folder)
    with pytest.raises(ValueError, match='conflicting'):
        objectives.migrate(monorepo, 'demo', apply=True)
    assert snapshot(folder) == before and source.exists()


def test_concurrent_writers_recheck_revisions_after_acquiring_lock(monorepo, seed_workspace):
    folder = seed_workspace()
    native(folder)
    expected = objectives.load(monorepo, 'demo')['revision']
    def write(name):
        try:
            objectives.mutate(monorepo, 'demo', {'type': 'settings', 'objective_id': 'phone', 'name': name}, expected)
            return 'saved'
        except ValueError as exc:
            assert 'changed elsewhere' in str(exc)
            return 'stale'
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(write, ['One', 'Two'])) == ['saved', 'stale']


def test_cli_migration_preview_apply_and_packaged_guide(monorepo, legacy):
    folder, source, original, doc = legacy
    runner = CliRunner()
    before = snapshot(folder)
    result = runner.invoke(objective_group, ['migrate', '--workspace', 'demo'])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)['migration_required'] and snapshot(folder) == before
    result = runner.invoke(objective_group, ['migrate', '--workspace', 'demo', '--apply'])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)['applied'] and not source.exists()
    from lab.commands.migrations import migrations_cmd
    result = runner.invoke(migrations_cmd, ['workspace-objectives'])
    assert result.exit_code == 0 and '.objective.json' in result.output
