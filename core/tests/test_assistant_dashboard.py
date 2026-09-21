"""Section JSON files are complete, ordered, validated, and conflict-safe."""
from copy import deepcopy
import json
from pathlib import Path
import pytest
from lab import assistant_dashboard as dashboard
from .test_assistant_documents_unified import library


def test_dashboard_persists_sections_as_independent_json(client, library):
    root, *_ = library
    originals = {path:path.read_bytes() for folder in ['tasks','notes','projects'] for path in (root/folder).glob('*.md')}
    first = client.get('/api/assistant').json()['dashboard']
    assert [row['id'] for row in first['sections']] == ['priority','starred','documents']
    assert first['sections'][0]['where'] == "source = 'open' AND (priority IN ('P1') OR due <= TODAY + 2)"
    assert not (root/'.assistant/dashboard').exists()
    assert all(set(row)==set(first['section_template']) for row in first['sections'])
    sections = deepcopy(first['sections'])
    sections[2].update(title='My meetings',where="kind = 'recurring' AND search CONTAINS 'team'",limit=0,position=-10)
    saved = client.put('/api/assistant/dashboard',json={'sections':sections,'expected':first['revision']})
    assert saved.status_code == 200,saved.text
    expected = sorted(sections,key=lambda row:row['position'])
    assert saved.json()['sections'] == expected
    directory = root/'.assistant/dashboard'
    assert {path.name for path in directory.glob('*.json')} == {'priority.json','starred.json','documents.json'}
    assert [json.loads((directory/(row['id']+'.json')).read_text()) for row in expected] == expected
    assert not (root/'.assistant/dashboard.json').exists()
    assert client.get('/api/assistant').json()['dashboard'] == saved.json()
    stale = client.put('/api/assistant/dashboard',json={'sections':[],'expected':first['revision']})
    assert stale.status_code == 409 and dashboard.read(root) == saved.json()
    assert all(path.read_bytes() == content for path,content in originals.items())
    # Editing one section does not rewrite the other section files.
    untouched = {path:(path.read_bytes(),path.stat().st_mtime_ns) for path in directory.glob('*.json') if path.stem!='documents'}
    changed=deepcopy(expected);changed[0]['title']='Renamed'
    renamed=dashboard.write(root,changed,expected=saved.json()['revision'])
    assert all((path.read_bytes(),path.stat().st_mtime_ns)==before for path,before in untouched.items())
    changed[0]['id']='renamed-section'
    renamed=dashboard.write(root,changed,expected=renamed['revision'])
    assert not (directory/'documents.json').exists() and (directory/'renamed-section.json').exists()
    empty = client.put('/api/assistant/dashboard',json={'sections':[],'expected':renamed['revision']})
    assert empty.status_code == 200 and dashboard.read(root)['sections'] == []
    assert directory.is_dir() and not list(directory.glob('*.json'))


@pytest.mark.parametrize('change', [
    {'title':''}, {'id':'../notes'}, {'limit':-5}, {'limit':True}, {'unknown':True},
    {'position':True}, {'position':1.5}, {'position':1000001}, {'schema':4}, {'schema':True},
    {'filter':{}}, {'filter':{'and':[]}}, {'filter':{'or':{}}}, {'filter':{'source':'bad'}},
    {'filter':{'priority':['bad']}}, {'filter':{'priority':[{}]}}, {'filter':{'priority':[]}},
    {'filter':{'due':{'within_days':-1,'include_overdue':True}}},
    {'filter':{'due':{'within_days':True,'include_overdue':True}}},
    {'filter':{'due':{'within_days':366,'include_overdue':True}}},
    {'filter':{'due':{'within_days':2,'include_overdue':'false'}}}, {'filter':{'due':{'within_days':2}}},
    {'filter':{'starred':'false'}}, {'filter':{'status':''}}, {'filter':{'kind':'bad'}},
    {'filter':{'search':'x'*501}}, {'filter':{'search':''}}, {'filter':{'workspace':False}},
    {'filter':{'source':'open','starred':True}}, {'filter':{'not':{'starred':True}}},
    {'filter':{'or':[{'starred':True}]*101}},
])
def test_invalid_dashboard_cannot_write(client,library,change):
    root,*_ = library
    first = dashboard.read(root)
    section = {**first['sections'][0],**change}
    if 'filter' in change:
        section.pop('where');section['schema']=2
    response = client.put('/api/assistant/dashboard',json={'sections':[section],'expected':first['revision']})
    assert response.status_code == 400,response.text
    assert not (root/'.assistant/dashboard').exists()


def test_missing_fields_duplicate_ids_and_excess_sections_are_rejected(client,library):
    root,*_ = library
    first = dashboard.read(root)
    incomplete = {key:value for key,value in first['sections'][0].items() if key!='limit'}
    for sections in [[incomplete],[first['sections'][0]]*2,[{**first['sections'][0],'id':str(i)} for i in range(31)]]:
        response = client.put('/api/assistant/dashboard',json={'sections':sections,'expected':first['revision']})
        assert response.status_code == 400


def test_legacy_layout_migrates_without_changing_custom_filters(client,library):
    root,*_ = library
    sections = [
        dict(dashboard.LEGACY_SECTION,id='starred',title='Starred',source='starred',kind='recurring'),
        dict(dashboard.LEGACY_SECTION,id='priority',title='Priority',source='open',priorities=['P0'],due_days=2),
    ]
    legacy=root/'.assistant/dashboard.json'
    legacy.write_text(json.dumps({'schema':1,'sections':sections}))
    original=legacy.read_bytes()
    before=dashboard.read(root)
    after=dashboard.migrate(root)
    assert before==after and legacy.read_bytes()==original
    for index,row in enumerate(after['sections']):
        assert row['position']==index*10
        assert row == dashboard.upgrade({**sections[index],'position':index*10})
    assert dashboard.migrate(root)==after
    # The separate files are authoritative, and external JSON edits refresh the API.
    source=root/'.assistant/dashboard/priority.json'
    changed=json.loads(source.read_text());changed['position']=-10;changed['title']='From JSON'
    source.write_text(json.dumps(changed))
    fresh=client.get('/api/assistant').json()['dashboard']
    assert fresh['sections'][0]==changed and fresh['revision']!=after['revision']
    stale=client.put('/api/assistant/dashboard',json={'sections':after['sections'],'expected':after['revision']})
    assert stale.status_code==409


def test_failed_file_write_keeps_previous_sections(library,monkeypatch):
    root,*_=library
    before=dashboard.migrate(root)
    directory=root/'.assistant/dashboard'
    originals={path:path.read_bytes() for path in directory.glob('*.json')}
    changed=deepcopy(before['sections'])
    for row in changed:row['title']+=' edited'
    write_json=dashboard.records.write_json
    count=0
    def fail_second(path,value):
        nonlocal count
        count+=1
        if count==2:raise OSError('Simulated write failure')
        return write_json(path,value)
    monkeypatch.setattr(dashboard.records,'write_json',fail_second)
    with pytest.raises(OSError,match='Simulated'):
        dashboard.write(root,changed,expected=before['revision'])
    assert all(path.read_bytes()==content for path,content in originals.items())
    assert dashboard.read(root)==before


def test_flat_section_files_upgrade_with_exact_backups(library):
    root,*_=library
    directory=root/'.assistant/dashboard';directory.mkdir()
    old=dict(dashboard.LEGACY_SECTION,id='focus',title='Focus',position=-10,source='open',
             priorities=['P0','P1'],due_days=2,overdue=False,match='all',workspace='demo')
    source=directory/'focus.json';source.write_text(json.dumps(old,indent=2))
    original=source.read_bytes()
    projected=dashboard.read(root)['sections'][0]
    assert source.read_bytes()==original  # reading projects the upgrade without writing
    assert projected['where']=="source = 'open' AND (priority IN ('P0', 'P1') AND due BETWEEN TODAY AND TODAY + 2) AND workspace = 'demo'"
    migrated=dashboard.migrate(root)
    assert json.loads(source.read_text())==projected
    backups=list((root/'.assistant/backups').glob('dashboard-schema-1-*/focus.json'))
    assert len(backups)==1 and backups[0].read_bytes()==original
    assert dashboard.migrate(root)==migrated


def test_deep_filter_is_rejected(library):
    root,*_=library
    first=dashboard.read(root)
    section={**first['sections'][0],'schema':2,'filter':{'source':'open'}}
    section.pop('where')
    for _ in range(10):section['filter']={'and':[section['filter']]}
    with pytest.raises(ValueError,match='depth'):
        dashboard.write(root,[section],expected=first['revision'])
