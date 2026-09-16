from pathlib import Path
import json

import pytest
from click.testing import CliRunner
from lab import assistant as db, assistant_records as records, assistant_migration as migration, assistant_meetings as meetings
from lab.cli import main


def seed(tmp_path):
    root = db.initialize(tmp_path / 'assistant')
    db.create_workspace(root, 'alpha', name='Alpha', vault='demo', vault_path=tmp_path, workspace_path=tmp_path/'alpha')
    db.create_workspace(root, 'beta', name='Beta', vault='demo', vault_path=tmp_path, workspace_path=tmp_path/'beta')
    task = db.create_task(root, 'Parent', workspace_id='alpha')
    child = db.create_subtask(root, 'Child', parent=task.stem, workspace='beta')
    meta, _ = db.read_markdown(task)
    meta['unknown'] = {'project': 'do not translate', 'nested':[1,2]}
    body = '\r\n# Context\r\n\r\nKeep trailing whitespace.  \r\n\r\n'
    task.write_bytes(records.encode_document(meta, body))
    series = meetings.create_series(root, 'weekly', workspace_id='alpha', title='Weekly')
    raw = tmp_path/'raw.txt';raw.write_bytes(b'  exact\r\nbytes\n\n')
    meeting = meetings.create_meeting(root,'Review',workspace_id='alpha',raw_file=raw,series=series.stem)
    content = meetings.create_content(root,'Question',meeting_id=meeting.stem,kind='question')
    return root,task,child,meeting,content,body,raw


def test_migration_preserves_bytes_relationships_aliases_and_backup(tmp_path):
    root,task,child,meeting,content,body,raw = seed(tmp_path)
    policy = b'# Client rules\r\n\r\nUse my own structure.  \r\n'
    for name in ('AGENTS.md', 'README.md'):
        (root/name).write_bytes(policy)
    originals = {str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()}
    original_paths = [str(p.relative_to(root)) for p in (task,child,meeting,content)]
    before = migration.migrate(root)
    assert before['dry_run'] is True and not (root/'tasks').exists()
    result = migration.migrate(root, dry_run=False)
    assert result['valid'] and result['counts'] == {'task':2,'note':3}
    assert records.verify(root)['task_roots'] == 1
    for name in ('AGENTS.md', 'README.md'):
        assert (root/name).read_bytes() == policy
    for path,data in originals.items():
        assert (Path(result['backup'])/path).read_bytes() == data
    for path in original_paths:
        assert records.resolve(root,path)[0].is_file()
    parent,metadata,after = db.find_task(root,task.stem)
    assert after == body
    assert metadata['unknown']['project'] == 'do not translate'
    child_meta = db.find_subtask(root,child.stem)[1]
    assert child_meta['parent'] == {'type':'task','id':task.stem}
    assert child_meta['workspace'] == 'beta'
    assert metadata['project'] is None and metadata['workspace'] == 'alpha'
    new_meeting = meetings.find_meeting(root,meeting.stem)[0]
    assert meetings.raw_path(root,new_meeting).read_bytes() == raw.read_bytes()
    assert list(meetings.iter_contents(root,new_meeting))[0]['id'] == content.stem
    assert migration.migrate(root,dry_run=False)['already_migrated']
    db.update_task(root,task.stem,'priority','P1')
    assert db.read_markdown(parent)[1] == body
    assert records.verify(root)['valid']


def test_failed_cutover_rolls_back_every_source(tmp_path):
    root,*_ = seed(tmp_path)
    original = {str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()}
    def fail(_): raise RuntimeError('simulated interruption')
    with pytest.raises(RuntimeError,match='simulated'):
        migration.migrate(root,dry_run=False,checkpoint=fail)
    assert not records.enabled(root)
    for path,data in original.items():
        assert (root/path).read_bytes() == data
    assert not (root/'tasks').exists()
    assert migration.migrate(root,dry_run=False)['valid']


def test_new_records_are_independent_and_completion_observes_descendants(tmp_path,monkeypatch):
    root,task,child,*_ = seed(tmp_path)
    migration.migrate(root,dry_run=False)
    monkeypatch.setenv('LAB_ASSISTANT_HOME',str(root))
    runner=CliRunner()
    for args in [ ['project','add','launch','--name','Launch'], ['add','Standalone'],
                  ['set',task.stem,'project','launch'], ['set',child.stem,'project','launch'],
                  ['note','add','Discussion','--parent',task.stem,'--parent-type','task','--kind','thread'] ]:
        result=runner.invoke(main,['assistant',*args]);assert result.exit_code == 0,result.output
    assert db.find_task(root,task.stem)[1]['workspace'] == 'alpha'
    assert db.find_subtask(root,child.stem)[1]['workspace'] == 'beta'
    with pytest.raises(ValueError,match='descendant'):
        db.update_task(root,task.stem,'status','done')
    db.update_subtask(root,child.stem,'status','done')
    db.update_task(root,task.stem,'status','done')
    with pytest.raises(ValueError,match='Reopen'):
        db.create_subtask(root,'Too late',parent=task.stem)
    with pytest.raises(ValueError,match='Reopen'):
        db.update_subtask(root,child.stem,'status','ready')
    with pytest.raises(ValueError,match='cycle'):
        records.update(root,task.stem,'parent',{'type':'task','id':child.stem})
    with pytest.raises(ValueError,match='Missing project'):
        db.update_task(root,task.stem,'project','missing')
    assert records.verify(root)['valid']


def test_duplicate_and_symlink_sources_stop_before_cutover(tmp_path):
    root,task,*_=seed(tmp_path)
    duplicate = root/'workspaces/beta/tasks'/task.name
    duplicate.parent.mkdir(exist_ok=True)
    meta,body=db.read_markdown(task);meta['workspace']='beta'
    db.write_markdown(duplicate,meta,body)
    with pytest.raises(ValueError,match='Duplicate'):
        migration.migrate(root,dry_run=False)
    assert task.is_file() and not (root/'tasks').exists()
    duplicate.unlink();duplicate.symlink_to(task)
    with pytest.raises(ValueError,match='symlinks'):
        migration.migrate(root,dry_run=False)
    assert task.is_file()


def test_recurring_task_keeps_independent_links_after_migration(tmp_path):
    from lab.assistant_recurrence import advance
    root, *_ = seed(tmp_path)
    migration.migrate(root, dry_run=False)
    project = records.create(root, 'project', 'Operations', identifier='operations')
    task = records.create(root, 'task', 'Monthly review', project=project.stem, workspace='beta',
                          recurrence='monthly', due='2026-01-31', status='ready')
    db.update_task(root, task.stem, 'status', 'done')
    following = advance(root, task.stem)
    metadata, _ = db.read_markdown(following)
    assert metadata['schema'] == 2 and metadata['due'] == '2026-02-28'
    assert metadata['project'] == 'operations' and metadata['workspace'] == 'beta'
    assert advance(root, task.stem) == following
    assert records.verify(root)['valid']
