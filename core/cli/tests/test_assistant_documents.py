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
    policy=b'# Client rules\r\n\r\nUse my own structure.  \r\n'
    for name in ('AGENTS.md','README.md'):
        (root/name).write_bytes(policy)
    before=list(records.records(root))
    original={row['path']:(root/row['path']).read_bytes() for row in before}
    assert documents.migrate(root)['subtabs']==2
    assert child.is_file()
    result=documents.migrate(root,dry_run=False)
    for name in ('AGENTS.md','README.md'):
        assert (root/name).read_bytes()==policy
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


def test_custom_attributes_cli_preserves_content_and_subtab_ownership(tmp_path,monkeypatch):
    root,task,child,note,standalone=seed(tmp_path)
    documents.migrate(root,dry_run=False)
    monkeypatch.setenv('LAB_ASSISTANT_HOME',str(root))
    before={row['id']:row['body'] for row in records.records(root)}
    runner=CliRunner()
    values={'is_RFC':True,'is_investigation':False,'tags':['draft'],'number':3,'result':None}
    for command,identifier in [([],task.stem),(['note'],standalone.stem),(['subtab'],note.stem)]:
        result=runner.invoke(main,['assistant',*command,'set',identifier,'attributes',json.dumps(values)])
        assert result.exit_code == 0,result.output
        assert records.resolve(root,identifier)[1]['attributes'] == values
    assert 'attributes' not in records.resolve(root,child.stem)[1]
    result=runner.invoke(main,['assistant','note','set',standalone.stem,'attributes','null'])
    assert result.exit_code == 0,result.output
    assert records.resolve(root,standalone.stem)[1]['attributes'] is None
    invalid=runner.invoke(main,['assistant','set',task.stem,'attributes','true'])
    assert invalid.exit_code != 0 and records.resolve(root,task.stem)[1]['attributes'] == values
    assert before == {row['id']:row['body'] for row in records.records(root)}
    assert records.verify(root)['valid']


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


def test_cli_root_tab_and_nested_subtab_share_the_markdown(tmp_path,monkeypatch):
    root,task,child,note,_=seed(tmp_path)
    documents.migrate(root,dry_run=False)
    monkeypatch.setenv('LAB_ASSISTANT_HOME',str(root))
    runner=CliRunner()
    created=runner.invoke(main,['assistant','subtab','add','Peer','--parent',task.stem,'--parent-type','task','--top-level'])
    assert created.exit_code==0,created.output
    peer=next(row for row in records.records(root) if row['title']=='Peer')
    assert peer['top_level'] is True and peer['parent']=={'type':'task','id':task.stem}
    assert documents.physical(root/peer['path'])==task
    assert peer['workspace']=='one'
    assert not records.resolve(root,child.stem)[1].get('top_level')
    assert not records.resolve(root,note.stem)[1].get('top_level')
    created=runner.invoke(main,['assistant','subtab','add','Nested','--parent',peer['id'],'--parent-type','note'])
    assert created.exit_code==0,created.output
    nested=next(row for row in records.records(root) if row['title']=='Nested')
    assert not nested.get('top_level') and nested['parent']['id']==peer['id']
    before=task.read_bytes()
    invalid=runner.invoke(main,['assistant','subtab','add','Invalid','--parent',peer['id'],'--parent-type','note','--top-level'])
    assert invalid.exit_code!=0 and 'document root' in invalid.output
    assert task.read_bytes()==before
    assert len(list((root/'tasks').glob('*.md')))==1 and len(list((root/'notes').glob('*.md')))==1


@pytest.mark.parametrize('record_type', ['task', 'note'])
def test_client_content_is_freeform_with_peer_and_nested_tabs(tmp_path, record_type):
    from lab import assistant_meetings as meetings
    from lab.assistant_recurrence import advance
    root=tmp_path/'assistant';root.mkdir()
    records.write_json(root/'.assistant/manifest.json',
                       {'schema':2,'state':'active','document_format':documents.FORMAT})
    records.add_workspace(root,'demo',name='Demo')
    main=(db.create_task(root,'Task',workspace_id='demo') if record_type=='task'
          else meetings.create_meeting(root,'Note',workspace_id='demo'))
    peer=records.create_subtab(root,'Peer',parent={'type':record_type,'id':main.stem},top_level=True)
    peer_id=records.read_document(peer)[0]['id']
    nested=records.create_subtab(root,'Nested',parent={'type':'note','id':peer_id})
    assert all(not row['body'].strip() for row in records.records(root))
    bodies=['No headings.\r\n\r\n自由な内容  \r\n',
            '## Mi estructura\n\n| A | B |\n|---|---|\n| 1 | 2 |\n',
            '<details><summary>Detalle</summary>\n\nTexto.\n\n</details>\n']
    for source,body in zip((main,peer,nested),bodies):
        records.write_document(source,records.read_document(source)[0],body)
    records.update(root,peer_id,'title','Renamed')
    for source,body in zip((main,peer,nested),bodies):
        assert records.read_document(source)[1]==body
        assert documents.physical(source)==main
    assert records.verify(root)['valid']
    if record_type=='task':
        records.update(root,peer_id,'status','skipped')
        records.update(root,main.stem,'recurrence','monthly')
        records.update(root,main.stem,'due','2028-01-31')
        following=advance(root,main.stem)
        assert records.read_document(following)[1]==''
        assert records.read_document(following)[0]['previous_task']==main.stem


def test_embedded_meeting_preview_accepts_any_headings(tmp_path):
    from lab import assistant_meetings as meetings
    root=tmp_path/'assistant';root.mkdir()
    records.write_json(root/'.assistant/manifest.json',
                       {'schema':2,'state':'active','document_format':documents.FORMAT})
    records.add_workspace(root,'demo',name='Demo')
    series=meetings.create_series(root,'weekly',workspace_id='demo',title='Series')
    note=meetings.create_meeting(root,'Note',workspace_id='demo',series='weekly')
    tab=meetings.create_content(root,'Tab',meeting_id=note.stem,kind='question')
    assert all(not records.read_document(source)[1].strip() for source in (series,note,tab))
    body='Introducción libre.\n\n## Mis pendientes\n\n- [ ] Revisar\n- [x] Listo\n\n```md\n- [ ] Ejemplo\n```\n'
    records.write_document(note,records.read_document(note)[0],body)
    row=next(records.note_rows(root,'meeting'))
    assert row['summary'].startswith('Introducción libre.')
    assert row['action_items_total']==2 and row['action_items_done']==1
    records.update(root,note.stem,'tldr','Descripción del cliente')
    assert next(records.note_rows(root,'meeting'))['summary']=='Descripción del cliente'
    assert records.read_document(note)[1]==body


def test_unified_cli_controls_existing_tasks_and_notes(tmp_path, monkeypatch):
    root,task,child,note,standalone=seed(tmp_path)
    documents.migrate(root,dry_run=False)
    monkeypatch.setenv('LAB_ASSISTANT_HOME',str(root))
    runner=CliRunner()
    def run(*args):
        result=runner.invoke(main,['assistant',*args])
        assert result.exit_code==0,result.output
        return result.output
    listing=run('document','ls')
    assert task.stem in listing and standalone.stem in listing and child.stem not in listing
    run('document','set',task.stem,'starred','true')
    assert task.stem in run('document','ls','--starred')
    run('document','set',standalone.stem,'track_task','true')
    assert standalone.stem in run('document','ls','--status','open')
    run('done',standalone.stem)
    assert standalone.stem in run('document','ls','--status','done')
    run('document','set',standalone.stem,'track_task','false')
    assert records.resolve(root,standalone.stem)[2]=='Independent note.'
    run('document','add','Team series','--kind','series')
    assert 'Team series' in run('document','ls','--kind','series')
    run('subtab','add','Work','--parent',standalone.stem,'--parent-type','note','--task')
    assert standalone.stem in run('document','ls','--status','open')
    assert records.verify(root)['valid']
