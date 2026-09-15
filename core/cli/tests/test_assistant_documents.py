import json
from pathlib import Path

import pytest
from click.testing import CliRunner
from lab import assistant as db, assistant_records as records, assistant_documents as documents
from lab.cli import main


def seed(tmp_path):
    root=tmp_path/'assistant'
    root.mkdir()
    for folder in ('tasks','notes','projects'):
        (root/folder).mkdir()
    records.write_json(root/'.assistant/manifest.json',{'schema':2,'state':'active'})
    records.add_workspace(root,'one',name='One')
    records.add_workspace(root,'two',name='Two')
    task=records.create(root,'task','Parent',workspace='one',body='# Context\r\n\r\nKeep me.  \r\n')
    child=records.create(root,'task','Child',parent={'type':'task','id':task.stem},workspace='two',body='# Child\n\nOriginal without newline')
    note=records.create(root,'note','Discussion',note_type='thread',parent={'type':'task','id':child.stem},body='# Notes\n\nDecisions.\n')
    standalone=records.create(root,'note','Standalone',body='Independent note.')
    return root,task,child,note,standalone


def test_embedded_migration_keeps_every_body_id_alias_and_backup(tmp_path):
    root,task,child,note,standalone=seed(tmp_path)
    before=list(records.records(root))
    original={row['path']:(root/row['path']).read_bytes() for row in before}
    assert documents.migrate(root)['subtabs']==2
    assert child.is_file()
    result=documents.migrate(root,dry_run=False)
    assert len(list((root/'tasks').glob('*.md')))==1
    assert len(list((root/'notes').glob('*.md')))==1
    for row in before:
        source,meta,body=records.resolve(root,row['path'])
        assert body==row['body'] and meta['id']==row['id']
        assert (Path(result['backup'])/row['path']).read_bytes()==original[row['path']]
        if row.get('parent'):
            assert documents.physical(source)==task and '#tab=' in str(source)
    assert documents.migrate(root,dry_run=False)['changed'] is False
    assert records.verify(root)['valid']
    assert len(list(db.iter_tasks(root)))==1
    assert records.resolve(root,child.stem)[1]['workspace']=='one'
    assert records.resolve(root,child.stem)[1]['legacy_metadata']['subtab_previous_links']['workspace']=='two'


def test_metadata_index_refreshes_after_cli_and_external_edits(tmp_path,monkeypatch):
    root,task,child,note,_=seed(tmp_path)
    documents.migrate(root,dry_run=False)
    original_body=records.resolve(root,note.stem)[2]
    records.update(root,note.stem,'due','2026-09-30')
    index=json.loads((root/'.assistant/index.json').read_text())
    assert next(r for r in index['records'] if r['id']==note.stem)['due']=='2026-09-30'
    assert records.resolve(root,note.stem)[2]==original_body
    task.write_bytes(task.read_bytes().replace(b'"Discussion"',b'"Updated externally"'))
    assert records.resolve(root,note.stem)[1]['title']=='Updated externally'
    assert 'Updated externally' in (root/'.assistant/index.json').read_text()
    (root/'.assistant/index.json').write_text('broken')
    assert records.verify(root)['valid']
    assert json.loads((root/'.assistant/index.json').read_text())['records']
    (root/'.assistant/index.json').unlink()
    assert records.verify(root)['valid'] and (root/'.assistant/index.json').is_file()
    monkeypatch.setenv('LAB_ASSISTANT_HOME',str(root))
    runner=CliRunner()
    for args in [['project','add','launch','--name','Launch'],['subtab','show',child.stem],['subtab','set',note.stem,'owner','Jesus'],
                 ['subtab','add','Follow-up','--parent',note.stem,'--parent-type','note']]:
        result=runner.invoke(main,['assistant',*args]);assert result.exit_code==0,result.output
    assert len(list((root/'tasks').glob('*.md')))==1 and len(list((root/'notes').glob('*.md')))==1
    assert records.resolve(root,note.stem)[1]['owner']=='Jesus'
    with pytest.raises(ValueError,match='changed elsewhere'):
        records.update(root,note.stem,'owner','Other',expected=None)


@pytest.mark.parametrize(('states','expected'),[
    (['not_started','not_started'],'not_started'),(['in_progress','not_started'],'in_progress'),
    (['done','not_started'],'in_progress'),(['skipped','not_started'],'in_progress'),
    (['done','skipped'],'done'),(['done','done'],'done'),(['skipped','skipped'],'done')])
def test_overall_status_truth_table(tmp_path,states,expected):
    root=tmp_path/'assistant';root.mkdir()
    records.write_json(root/'.assistant/manifest.json',{'schema':2,'state':'active','document_format':documents.FORMAT})
    task=records.create(root,'task','Parent')
    children=[records.create_subtab(root,str(i),parent={'type':'task','id':task.stem}) for i in range(2)]
    for child,status in zip(children,states):
        records.update(root,str(child.relative_to(root)),'status',status)
    assert next(db.iter_tasks(root))['status']==expected
    records.update(root,task.stem,'status','cancelled')
    assert next(db.iter_tasks(root))['status']=='cancelled'
    records.update(root,task.stem,'status',expected)
    assert next(db.iter_tasks(root))['status']==expected


def test_nested_progress_reopen_and_skip_branch(tmp_path):
    root,task,child,note,standalone=seed(tmp_path)
    documents.migrate(root,dry_run=False)
    records.update(root,note.stem,'status','done')
    assert next(db.iter_tasks(root))['status']=='done'
    records.update(root,note.stem,'status','in_progress')
    assert next(db.iter_tasks(root))['status']=='in_progress'
    records.update(root,child.stem,'status','skipped')
    assert next(db.iter_tasks(root))['status']=='done'
    records.update(root,task.stem,'status','cancelled')
    records.update(root,task.stem,'status','done')
    assert next(db.iter_tasks(root))['status']=='done'
    with pytest.raises(ValueError,match='calculated'):
        records.update(root,task.stem,'status','not_started')
    with pytest.raises(ValueError,match='same Markdown'):
        records.update(root,note.stem,'parent',{'type':'note','id':standalone.stem})
    with pytest.raises(ValueError,match='cycle'):
        records.update(root,child.stem,'parent',{'type':'note','id':note.stem})


def test_failed_embedded_cutover_rolls_back(tmp_path,monkeypatch):
    root,*_=seed(tmp_path)
    before={str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*.md')}
    original=documents.snapshot
    monkeypatch.setattr(documents,'snapshot',lambda *a,**k: (_ for _ in ()).throw(ValueError('simulated')))
    with pytest.raises(ValueError,match='simulated'):
        documents.migrate(root,dry_run=False)
    assert not documents.enabled(root)
    for path,data in before.items():assert (root/path).read_bytes()==data
    monkeypatch.setattr(documents,'snapshot',original)
    assert documents.migrate(root,dry_run=False)['changed']


def test_embedded_parent_properties_preserve_subtab_bodies_and_links(tmp_path):
    root,task,child,note,_=seed(tmp_path)
    documents.migrate(root,dry_run=False)
    before={row['id']:row['body'] for row in records.records(root)}
    records.create(root,'project','Launch',identifier='launch',status='active')
    records.update(root,task.stem,'project','launch')
    records.update(root,task.stem,'workspace','two')
    for identifier,body in before.items():
        _,metadata,current=records.resolve(root,identifier)
        assert current==body
        if identifier in {child.stem,note.stem}:
            assert metadata['project']=='launch' and metadata['workspace']=='two'
    with pytest.raises(ValueError,match='inherit'):
        records.update(root,note.stem,'workspace','one')


def test_external_editor_can_save_crlf_markers(tmp_path):
    root,task,child,note,_=seed(tmp_path)
    documents.migrate(root,dry_run=False)
    task.write_bytes(task.read_bytes().replace(b'\r\n',b'\n').replace(b'\n',b'\r\n'))
    assert records.resolve(root,note.stem)[2]=='# Notes\r\n\r\nDecisions.\r\n'
    records.update(root,note.stem,'priority','P1')
    assert records.resolve(root,note.stem)[2]=='# Notes\r\n\r\nDecisions.\r\n'
