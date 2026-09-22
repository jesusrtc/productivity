"""Production task migration, lifecycle, content preservation and dashboard continuity."""
import hashlib
import json
import pytest
from lab import assistant_documents as documents, assistant_records as records, assistant_tasks as tasks
from lab import assistant_migration as migration, assistant_storage as storage, assistant_dashboard as dashboard
from .test_assistant_routes import _seed


@pytest.fixture()
def legacy_tasks(monkeypatch,tmp_path,monorepo):
    root,_=_seed(monkeypatch,tmp_path,monorepo)
    migration.migrate(root,dry_run=False)
    documents.migrate(root,dry_run=False)
    storage.migrate(root,dry_run=False)
    note=records.create(root,'note','Task document',body='# Notes\n\nNotes stay.\n\n- [ ] Call Alex\n  - [x] Find number\n  - [ ] Pick a time\n\n```md\n- [ ] Example only\n```\n',starred=True,custom={'keep':True})
    context=records.create_subtab(root,'Context',parent={'type':'note','id':note.stem},track_task=True)
    records.update(root,str(context.relative_to(root)),'priority','P1')
    child=records.create_subtab(root,'Research',parent={'type':'note','id':records.resolve(root,str(context.relative_to(root)))[1]['id']})
    records.update_body(root,str(child.relative_to(root)),'Research body.\n\n- [ ] Read source\n',expected='')
    series=records.create(root,'note','Weekly series',note_type='series',starred=True)
    meeting=records.create(root,'note','Weekly note',note_type='meeting',series=series.stem,starred=True,body='Meeting body.\n')
    dashboard.read(root)
    return root,note,context,child,series,meeting


@pytest.fixture()
def owned_tasks(legacy_tasks):
    tasks.migrate(legacy_tasks[0],dry_run=False)
    return legacy_tasks


def test_migration_preserves_identity_notes_stars_dashboard_and_is_idempotent(legacy_tasks):
    root,note,context,child,series,meeting=legacy_tasks
    before={row['id']:row for row in records.records(root)}
    config={p.relative_to(root).as_posix():p.read_bytes() for p in (root/'.assistant/dashboard').glob('*.json')}
    dry=tasks.migrate(root)
    assert dry['tasks'] >= 6 and not dry['applied']
    assert records.read_document(note)[0].get('task_format') is None
    applied=tasks.migrate(root,dry_run=False)
    assert applied['applied'] and records.verify(root)['valid']
    after={row['id']:row for row in records.records(root)}
    assert set(before)==set(after)
    for identifier,old in before.items():
        current=after[identifier]
        for field in ('title','id','type','created','parent','starred','series','aliases','external_url','custom','position'):
            assert current.get(field)==old.get(field),(identifier,field)
        expected,checkboxes=tasks.convert_checkboxes(old['body'],identifier,None,'P2')
        assert current['body']==expected
        assert not records.tracks_task(current)
    assert config=={key:(root/key).read_bytes() for key in config}
    data=tasks.view(root,note.stem)
    assert len(data['tasks'])==5
    parent=next(task for task in data['tasks'] if task['title']=='Call Alex')
    nested=[task for task in data['tasks'] if task.get('parent_id')==parent['id']]
    assert len(nested)==2 and parent['status']=='in_progress'
    assert {task['status'] for task in nested}=={'done','not_started'}
    assert not any(task['title']=='Example only' for task in data['tasks'])
    assert after[note.stem]['custom']=={'keep':True}
    backup=applied['backup']
    journal=json.loads(__import__('pathlib').Path(applied['journal']).read_text())
    for path,digest in journal['sha256'].items():
        assert hashlib.sha256((__import__('pathlib').Path(backup)/path).read_bytes()).hexdigest()==digest
    bytes_before={p:p.read_bytes() for p in (root/'documents').glob('*.md')}
    assert tasks.migrate(root,dry_run=False)['noop']
    assert bytes_before=={p:p.read_bytes() for p in bytes_before}


def test_task_api_edits_create_subtasks_and_preserve_content_and_properties(client,owned_tasks):
    root,note,context,child,*_=owned_tasks
    old=documents.unpack(note.read_bytes())
    data=tasks.view(root,note.stem)
    def change(values,task_id=None):
        nonlocal data
        response=client.post('/api/assistant/document-task',json={'document_id':note.stem,'expected':data['revision'],'task_id':task_id,'values':values})
        assert response.status_code==200,response.text
        data=response.json()
        return next(task for task in data['tasks'] if task['id']==data['task_id'])
    simple=change({'title':'Simple task','priority':'P0'})
    assert simple['tab_id'] is None
    nested=change({'title':'Ordinary subtask','parent_id':simple['id']})
    assert nested['parent_id']==simple['id']
    simple=change({'status':'in_progress','due':'2026-10-01','owner':'Jesus','recurrence':'weekly'},simple['id'])
    assert next(task for task in data['tasks'] if task['id']==nested['id'])['status']=='not_started'
    change({'done':True},nested['id'])
    assert next(task for task in data['tasks'] if task['id']==simple['id'])['status']=='done'
    change({'done':False,'tab_id':records.resolve(root,str(child.relative_to(root)))[1]['id']},nested['id'])
    change({'title':'Renamed','priority':'P1'},simple['id'])
    meta,body,tabs=documents.unpack(note.read_bytes())
    assert body==old[1] and tabs==old[2] and meta['starred'] and meta['custom']==old[0]['custom']
    assert len(tabs)==2
    listing=client.get('/api/assistant').json()
    assert 'blocked' in listing['statuses'] and 'skipped' in listing['statuses']
    row=next(row for row in listing['documents'] if row['id']==note.stem)
    assert row['tracked'] and row['task_summary']['pending']>0 and 'Renamed' in row['search_text']
    detail=client.get('/api/assistant/note',params={'path':str(child.relative_to(root))}).json()
    assert detail['document_tasks']['revision']==data['revision']
    assert not detail['tree']['track_task']
    assert detail['body']==tabs[1][1]


def test_conflicts_invalid_links_cycles_and_unrelated_fields_never_write(client,owned_tasks):
    root,note,*_=owned_tasks
    data=tasks.view(root,note.stem)
    task=data['tasks'][0]
    before=note.read_bytes()
    base={'document_id':note.stem,'expected':data['revision'],'task_id':task['id'],'values':{}}
    for values in [{'tab_id':'missing'},{'parent_id':task['id']},{'priority':'P9'},{'status':'invalid'},{'title':' '},{'starred':False},{'done':'yes'},{'tab_id':[]},{'due':'not a date'},{'status':{}},{'priority':[]}]:
        response=client.post('/api/assistant/document-task',json=base|{'values':values})
        assert response.status_code==400,response.text
        assert note.read_bytes()==before
    assert client.post('/api/assistant/document-task',json=base|{'expected':'stale','values':{'done':True}}).status_code==409
    assert note.read_bytes()==before
    records.update(root,note.stem,'starred',False)
    assert client.post('/api/assistant/document-task',json=base|{'values':{'done':True}}).status_code==409
    assert not records.resolve(root,note.stem)[1]['starred']


def test_new_documents_tabs_and_legacy_commands_use_json_tasks(owned_tasks):
    root,note,*_=owned_tasks
    created=records.create(root,'task','New work',due='2026-10-02',priority='P1')
    meta,_=documents.read(created)
    assert meta['task_format']==tasks.FORMAT and not meta['track_task']
    assert len(meta['tasks'])==1 and meta['tasks'][0]['due']=='2026-10-02'
    records.update(root,created.stem,'status','done')
    assert tasks.view(root,created.stem)['tasks'][0]['status']=='done'
    tab=records.create_subtab(root,'Content peer',parent={'type':'note','id':note.stem},top_level=True)
    nested=records.create_subtab(root,'Nested content',parent={'type':'note','id':records.resolve(root,str(tab.relative_to(root)))[1]['id']})
    before=tasks.view(root,note.stem)['tasks']
    records.update_body(root,str(nested.relative_to(root)),'New content',expected='')
    assert tasks.view(root,note.stem)['tasks']==before
    assert records.resolve(root,str(nested.relative_to(root)))[2]=='New content'
    assert records.verify(root)['valid']
    with pytest.raises(ValueError,match='Tabs are content'):
        records.update(root,str(tab.relative_to(root)),'track_task',True)


def test_migration_rolls_back_an_interrupted_write(legacy_tasks,monkeypatch):
    root,*_=legacy_tasks
    originals={path:path.read_bytes() for path in (root/'documents').glob('*.md')}
    manifest=(root/'.assistant/manifest.json').read_bytes()
    write=records.atomic_bytes
    failed=False
    def fail_once(path,data):
        nonlocal failed
        if path.parent==root/'documents' and not failed:
            failed=True
            raise OSError('injected write failure')
        return write(path,data)
    monkeypatch.setattr(records,'atomic_bytes',fail_once)
    with pytest.raises(OSError,match='injected'):
        tasks.migrate(root,dry_run=False)
    assert originals=={path:path.read_bytes() for path in originals}
    assert (root/'.assistant/manifest.json').read_bytes()==manifest
    assert records.verify(root)['valid']


def test_recurrence_and_cli_keep_work_in_the_same_document(owned_tasks,monkeypatch):
    from click.testing import CliRunner
    from lab.commands.assistant import assistant_group
    from lab import assistant_recurrence as recurrence
    root,note,*_=owned_tasks
    monkeypatch.setenv('LAB_ASSISTANT_HOME',str(root))
    runner=CliRunner()
    result=runner.invoke(assistant_group,['task','add','Pay bill','--document',note.stem,'--due','2026-01-31'])
    assert result.exit_code==0,result.output
    identifier=result.output.strip()
    for field,value in [('priority','P0'),('recurrence','monthly'),('status','done')]:
        result=runner.invoke(assistant_group,['task','set',note.stem,identifier,field,value])
        assert result.exit_code==0,result.output
    before_files=set((root/'documents').glob('*.md'))
    path=recurrence.advance(root,identifier)
    assert path==note
    repeated=next(task for task in tasks.view(root,note.stem)['tasks'] if task.get('previous_task')==identifier)
    assert repeated['due']=='2026-02-28' and repeated['status']=='not_started' and repeated['priority']=='P0'
    assert tasks.repeat(root,note.stem,identifier)['task_id']==repeated['id']
    assert set((root/'documents').glob('*.md'))==before_files
    result=runner.invoke(assistant_group,['done',repeated['id']])
    assert result.exit_code==0,result.output
    assert tasks.view(root,note.stem)['tasks'][-1]['status']=='done'


def test_skipped_branches_preserve_completion_on_migration(legacy_tasks):
    root,note,context,*_=legacy_tasks
    records.update_body(root,str(context.relative_to(root)),'- [ ] Unfinished detail\n',expected='')
    records.update(root,str(context.relative_to(root)),'status','skipped')
    tasks.migrate(root,dry_run=False)
    converted=tasks.view(root,note.stem)['tasks']
    task=next(task for task in converted if task['id']==records.resolve(root,str(context.relative_to(root)))[1]['id'])
    assert task['status']=='skipped'
    assert all(child['status']=='skipped' for child in converted if child.get('parent_id')==task['id'])


def test_adding_a_subtask_preserves_explicit_wip(owned_tasks):
    root,note,*_=owned_tasks
    added=tasks.change(root,note.stem,{'title':'Active work','status':'in_progress'})
    parent=added['task_id']
    result=tasks.change(root,note.stem,{'title':'New step','parent_id':parent})
    assert next(task for task in result['tasks'] if task['id']==parent)['status']=='in_progress'
    assert next(task for task in result['tasks'] if task['id']==result['task_id'])['status']=='not_started'
