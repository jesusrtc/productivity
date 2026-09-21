from lab import assistant as db, assistant_migration as migration, assistant_records as records, assistant_meetings as meetings
from .test_assistant_routes import _seed


def test_migrated_aliases_metadata_assets_and_tree(client, monkeypatch, tmp_path, monorepo):
    root,task=_seed(monkeypatch,tmp_path,monorepo)
    child=db.create_subtask(root,'Child',parent=task.stem)
    raw=tmp_path/'raw.txt';raw.write_bytes(b' Keep\r\n')
    note=meetings.create_meeting(root,'Review',workspace_id='demo',raw_file=raw)
    content=meetings.create_content(root,'Question',meeting_id=note.stem,kind='question')
    asset=task.parent/'asset.txt';asset.write_text('original asset')
    oldtask=task.relative_to(root).as_posix()
    oldcontent=content.relative_to(root).as_posix()
    oldnote=note.relative_to(root).as_posix()
    migration.migrate(root,dry_run=False)
    files=client.get('/api/workspace-files',params={'path':str(root)}).json()
    assert {'tasks','notes','projects'} <= {row['path'] for row in files if row['type']=='dir'}
    index=client.get('/api/assistant').json()
    assert index['schema']==2 and len(index['tasks'])==2
    detail=client.get('/api/assistant/task',params={'path':oldtask}).json()
    assert detail['path']=='tasks/'+task.name
    assert detail['tree']['children'][0]['id']==child.stem
    assert client.get('/api/assistant/meeting-content',params={'path':oldcontent}).status_code==200
    note_detail=client.get('/api/assistant/meeting',params={'path':oldnote}).json()
    assert note_detail['contents'][0]['id']==content.stem
    original=client.get('/api/assistant/meeting-content',params={'path':note_detail['raw']['path']})
    assert original.json()['body']==raw.read_bytes().decode()
    result=client.get('/api/assistant/asset',params={'task':oldtask,'src':'asset.txt'})
    assert result.status_code==200 and result.text=='original asset'
    project=client.post('/api/assistant/record',json={'type':'project','title':'Launch'}).json()
    result=client.patch('/api/assistant/metadata',json={'path':oldtask,'field':'project','expected':None,'value':project['metadata']['id']})
    assert result.status_code==200,result.text
    assert result.json()['metadata']['workspace']=='demo'
    stale=client.patch('/api/assistant/metadata',json={'path':oldtask,'field':'project','expected':None,'value':None})
    assert stale.status_code==409
    assert client.get('/api/assistant/task',params={'path':'../AGENTS.md'}).status_code==400
    assert records.verify(root)['valid']


def test_new_note_threads_are_openable_and_parent_is_validated(client, monkeypatch, tmp_path, monorepo):
    root,task=_seed(monkeypatch,tmp_path,monorepo)
    migration.migrate(root,dry_run=False)
    response=client.post('/api/assistant/record',json={'type':'note','title':'Discussion','parent':{'type':'task','id':task.stem}})
    assert response.status_code==200,response.text
    note=response.json()
    assert note['root_path']=='tasks/'+task.name
    assert client.get('/api/assistant/note',params={'path':note['path']}).json()['body']==''
    bad=client.post('/api/assistant/record',json={'type':'note','title':'Invalid','parent':{'type':'task','id':'missing'}})
    assert bad.status_code==400


def test_embedded_subtabs_metadata_index_progress_and_legacy_links(client, monkeypatch, tmp_path, monorepo):
    from lab import assistant_documents as documents
    root,task=_seed(monkeypatch,tmp_path,monorepo)
    migration.migrate(root,dry_run=False)
    documents.migrate(root,dry_run=False)
    created=client.post('/api/assistant/record',json={'type':'subtab','title':'Research','parent':{'type':'task','id':task.stem}})
    assert created.status_code==200,created.text
    child=created.json()
    assert child['path'].startswith('tasks/'+task.name+'#tab=')
    assert len(list((root/'tasks').glob('*.md')))==1 and not list((root/'notes').glob('*.md'))
    for field,value in [('tldr','Find the facts'),('due','2026-09-30'),('owner','Jesus'),('priority','P1'),('status','skipped')]:
        changed=client.patch('/api/assistant/metadata',json={'path':child['path'],'field':field,'expected':child['metadata'].get(field),'value':value})
        assert changed.status_code==200,changed.text
        child=changed.json()
    overall=client.get('/api/assistant/task',params={'path':'tasks/'+task.name}).json()
    assert overall['progress']['status']=='done'
    assert overall['tree']['children'][0]['description']=='Find the facts'
    assert client.get('/api/assistant').json()['tasks'][0]['status']=='done'
    index=__import__('json').loads((root/'.assistant/index.json').read_text())
    assert next(r for r in index['records'] if r['id']==child['metadata']['id'])['owner']=='Jesus'
    cancelled=client.patch('/api/assistant/metadata',json={'path':'tasks/'+task.name,'field':'status','expected':overall['metadata']['status'],'value':'cancelled'})
    assert cancelled.status_code==200,cancelled.text
    assert cancelled.json()['progress']['status']=='cancelled'
    stale=client.patch('/api/assistant/metadata',json={'path':child['path'],'field':'owner','expected':None,'value':'Other'})
    assert stale.status_code==409
    assert client.get('/api/assistant/note',params={'path':child['path']}).json()['metadata']['due']=='2026-09-30'
    assert client.get('/api/assistant/task',params={'path':'../tasks/'+task.name}).status_code==400


def test_embedded_markdown_links_open_the_subtab(client, monkeypatch, tmp_path, monorepo):
    from lab import assistant_documents as documents
    from urllib.parse import urlparse, parse_qs
    root,task=_seed(monkeypatch,tmp_path,monorepo)
    migration.migrate(root,dry_run=False)
    old_child=records.create(root,'note','Sources',parent={'type':'task','id':task.stem})
    alias=str(old_child.relative_to(root))
    documents.migrate(root,dry_run=False)
    target=str(records.resolve(root,old_child.stem)[0].relative_to(root))
    for src in ['#tab='+old_child.stem,task.name+'#tab='+old_child.stem,'../'+alias]:
        response=client.get('/api/assistant/link',params={'document':'tasks/'+task.name,'src':src},follow_redirects=False)
        assert response.status_code==307,response.text
        assert parse_qs(urlparse(response.headers['location']).query)['note']==[target]


def test_root_level_tab_placement_stays_in_document_and_tracks_progress(client, monkeypatch, tmp_path, monorepo):
    from lab import assistant_documents as documents
    root,task=_seed(monkeypatch,tmp_path,monorepo)
    migration.migrate(root,dry_run=False)
    documents.migrate(root,dry_run=False)
    parent={'type':'task','id':task.stem}
    peer=client.post('/api/assistant/record',json={'type':'subtab','title':'Peer','parent':parent,'top_level':True})
    assert peer.status_code==200,peer.text
    peer=peer.json()
    assert peer['metadata']['top_level'] is True
    assert peer['metadata']['parent']==parent
    assert peer['path'].startswith('tasks/'+task.name+'#tab=')
    nested_parent={'type':'note','id':peer['metadata']['id']}
    nested=client.post('/api/assistant/record',json={'type':'subtab','title':'Nested','parent':nested_parent}).json()
    assert not nested['metadata'].get('top_level')
    assert nested['metadata']['parent']==nested_parent
    assert nested['tree']['children'][0]['top_level'] is True
    assert nested['tree']['children'][0]['children'][0]['id']==nested['metadata']['id']
    before=(root/'tasks'/task.name).read_bytes()
    invalid=client.post('/api/assistant/record',json={'type':'subtab','title':'Invalid','parent':nested_parent,'top_level':True})
    assert invalid.status_code==400
    assert (root/'tasks'/task.name).read_bytes()==before
    assert len(list((root/'tasks').glob('*.md')))==1 and not list((root/'notes').glob('*.md'))
    for status in ['in_progress','skipped']:
        changed=client.patch('/api/assistant/metadata',json={'path':nested['path'],'field':'status','expected':nested['metadata'].get('status'),'value':status})
        assert changed.status_code==200,changed.text
        nested=changed.json()
        assert nested['tree']['progress']['status']==('done' if status=='skipped' else status)
    assert records.verify(root)['valid']
