"""One library, optional task tracking, and independent document/series stars."""
import pytest

from lab import assistant_records as records, assistant_documents as documents, assistant_migration as migration
from .test_assistant_routes import _seed


@pytest.fixture()
def library(monkeypatch, tmp_path, monorepo):
    root, task = _seed(monkeypatch, tmp_path, monorepo)
    migration.migrate(root, dry_run=False)
    documents.migrate(root, dry_run=False)
    task = records.resolve(root, task.stem)[0]
    note = records.create(root, 'note', 'Guide', body='The actual guide.\n', custom={'preserve':True})
    content = records.create_subtab(root, 'Reference', parent={'type':'note','id':note.stem})
    work = records.create_subtab(root, 'Review guide', parent={'type':'note','id':note.stem}, track_task=True)
    series = records.create(root, 'note', 'Team meetings', note_type='series')
    meeting = records.create(root, 'note', 'Weekly sync', note_type='meeting', series=series.stem)
    return root, task, note, content, work, series, meeting


def change(client, root, source, field, value):
    ref = str(source.relative_to(root))
    before = records.resolve(root, ref)[1].get(field)
    response = client.patch('/api/assistant/metadata', json={'path':ref,'field':field,'value':value,'expected':before})
    assert response.status_code == 200, response.text
    return response.json()


def test_library_contains_existing_tasks_notes_and_series_once(client, library):
    root, task, note, content, work, series, meeting = library
    listing = client.get('/api/assistant').json()
    rows = {row['id']:row for row in listing['documents']}
    assert len(rows) == len(listing['documents']) == 4
    assert rows[task.stem]['tracked'] and not rows[task.stem]['keep_in_documents']
    assert rows[note.stem]['keep_in_documents'] and rows[note.stem]['tracked']
    assert rows[note.stem]['progress']['total'] == 1
    assert rows[meeting.stem]['kind'] == 'meeting'
    assert rows[series.stem]['meeting_count'] == 1
    assert {row['id'] for row in listing['tasks']} == {task.stem,note.stem}
    assert rows[note.stem]['search_text'].find('Review guide') >= 0
    detail = client.get('/api/assistant/note',params={'path':str(content.relative_to(root))}).json()
    assert detail['progress']['status'] is None and not detail['progress']['tracked']


def test_complete_work_retains_document_and_reopening_reactivates_it(client, library):
    root, task, note, content, work, *_ = library
    change(client,root,work,'status','done')
    row = next(row for row in client.get('/api/assistant').json()['documents'] if row['id']==note.stem)
    assert row['status']=='done' and row['keep_in_documents']
    assert records.read_document(note)[1]=='The actual guide.\n'
    assert records.read_document(content)[1]==''
    change(client,root,work,'status','not_started')
    assert next(row for row in client.get('/api/assistant').json()['documents'] if row['id']==note.stem)['status']=='not_started'
    change(client,root,work,'track_task',False)
    row = next(row for row in client.get('/api/assistant').json()['documents'] if row['id']==note.stem)
    assert not row['tracked'] and row['status'] is None
    assert records.read_document(work)[0]['status']=='not_started'  # history is retained
    assert records.verify(root)['valid']


def test_starring_series_and_note_is_independent_and_conflict_safe(client, library):
    root, _, note, _, _, series, meeting = library
    original = {row['id']:row['body'] for row in records.records(root)}
    change(client,root,series,'starred',True)
    listing = client.get('/api/assistant').json()['documents']
    assert {row['id'] for row in listing if row['starred']} == {series.stem}
    change(client,root,meeting,'starred',True)
    change(client,root,series,'starred',False)
    assert {row['id'] for row in client.get('/api/assistant').json()['documents'] if row['starred']} == {meeting.stem}
    stale = client.patch('/api/assistant/metadata',json={'path':str(meeting.relative_to(root)), 'field':'starred','value':False,'expected':None})
    assert stale.status_code == 409
    assert original == {row['id']:row['body'] for row in records.records(root)}
    assert records.read_document(note)[0]['custom']=={'preserve':True}


def test_label_and_retention_preserve_identity_content_and_tabs(client, library):
    root, task, note, content, work, series, meeting = library
    before=records.read_document(note)
    detail=change(client,root,note,'note_type','meeting')
    assert detail['root_kind']=='meeting' and len(detail['tree']['children'])==2
    assert detail['metadata']['id']==before[0]['id'] and detail['metadata']['created']==before[0]['created']
    assert detail['body']==before[1]
    change(client,root,note,'series',series.stem)
    assert next(row for row in client.get('/api/assistant').json()['documents'] if row['id']==series.stem)['meeting_count']==2
    change(client,root,note,'note_type','plain')
    assert records.read_document(note)[0]['series']==series.stem  # changing a label does not erase membership
    change(client,root,task,'keep_in_documents',True)
    assert next(row for row in client.get('/api/assistant').json()['documents'] if row['id']==task.stem)['keep_in_documents']
    detail=change(client,root,task,'note_type','meeting')
    assert detail['root_kind']=='meeting' and detail['path'].startswith('tasks/')
    assert client.get('/api/assistant/meeting',params={'path':detail['path']}).status_code==200
    invalid=client.patch('/api/assistant/metadata',json={'path':str(series.relative_to(root)),'field':'note_type','value':'plain','expected':'series'})
    assert invalid.status_code==400 and records.read_document(series)[0]['note_type']=='series'


@pytest.mark.parametrize('field,value',[('starred','false'),('starred',None),('track_task','true'),('keep_in_documents','no'),('note_type','unknown'),('series',True)])
def test_bad_metadata_cannot_mutate_documents(client,library,field,value):
    root, _, note, *_ = library
    before=note.read_bytes()
    response=client.patch('/api/assistant/metadata',json={'path':str(note.relative_to(root)),'field':field,'value':value,'expected':records.read_document(note)[0].get(field)})
    assert response.status_code==400
    assert note.read_bytes()==before


def test_task_content_is_editable_in_same_document(client,library):
    root, task, *_ = library
    metadata,body=records.read_document(task)
    response=client.put('/api/assistant/content',json={'path':str(task.relative_to(root)),'expected':body,'body':'The resulting document.'})
    assert response.status_code==200,response.text
    assert response.json()['metadata']['id']==metadata['id']
    assert response.json()['body']=='The resulting document.'


def test_external_document_api_preserves_content_and_checks_conflicts(client, library):
    root, _, note, content, work, series, meeting = library
    before = {row['id']:row['body'] for row in records.records(root)}
    url = 'https://docs.google.com/document/d/example/edit'
    for source in (note,content,series,meeting):
        detail = change(client,root,source,'external_url',url)
        assert detail['metadata']['external_url'] == url
    listing = client.get('/api/assistant').json()['documents']
    assert all(next(row for row in listing if row['id']==source.stem)['external_url']==url for source in (note,series,meeting))
    ref = note.relative_to(root).as_posix()
    stale = client.patch('/api/assistant/metadata',json={'path':ref,'field':'external_url','value':None,'expected':None})
    assert stale.status_code == 409
    for value in ['javascript:alert(1)','file:///tmp/document','https://user:secret@example.com']:
        invalid = client.patch('/api/assistant/metadata',json={'path':ref,'field':'external_url','value':value,'expected':url})
        assert invalid.status_code == 400
    change(client,root,note,'external_url',None)
    assert not records.read_document(work)[0].get('external_url')
    assert before == {row['id']:row['body'] for row in records.records(root)}


def test_unified_paths_keep_legacy_routes_and_relative_assets(client, library):
    from lab import assistant_storage as storage
    from core.routes import assistant_v2
    root,task,note,content,*_ = library
    (root/'notes/attachment.txt').write_text('Source attachment')
    oldref = note.relative_to(root).as_posix()
    records.update_body(root,oldref,'[Other]('+note.name+'#tab='+str(content).split('#tab=')[1]+')\n![Asset](attachment.txt)',expected='The actual guide.\n')
    records.update(root,oldref,'external_url','https://example.com/document')
    storage.migrate(root,dry_run=False)
    result = client.get('/api/assistant/note',params={'path':oldref})
    assert result.status_code == 200 and result.json()['path'].startswith('documents/')
    assert result.json()['metadata']['external_url'] == 'https://example.com/document'
    for source,route in [(task,'task'),(note,'note'),(content,'note')]:
        response = client.get('/api/assistant/'+route,params={'path':source.relative_to(root).as_posix()})
        assert response.status_code == 200 and response.json()['path'].startswith('documents/')
    target,_,_ = assistant_v2.local_target(root,oldref,'attachment.txt')
    assert target.read_text() == 'Source attachment'
    target,meta,_ = assistant_v2.local_target(root,oldref,note.name+'#tab='+str(content).split('#tab=')[1])
    assert meta['id'] == str(content).split('#tab=')[1]
    change(client,root,note,'external_url','https://example.com/updated')
    listing = client.get('/api/assistant').json()['documents']
    assert all(row['path'].startswith('documents/') for row in listing)
    assert records.verify(root)['valid']
