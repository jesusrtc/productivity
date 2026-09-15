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
