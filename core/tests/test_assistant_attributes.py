"""Custom attributes round-trip as JSON without altering client content."""
from copy import deepcopy

import pytest
from lab import assistant_records as records, assistant_attributes as attributes, assistant_dashboard as dashboard
from .test_assistant_documents_unified import library, change


def test_attributes_on_tasks_notes_and_tabs_preserve_content_and_identity(client, library):
    root, task, note, content, work, *_ = library
    before = {row['id']:deepcopy(row) for row in records.records(root)}
    value = {'is_investigation':True, 'is_RFC':False, 'stage':'Review', 'score':2.5,
             'tags':['internal','draft'], 'result':None, 'extra':{'approved':False}}
    for source in (task,note,content,work):
        saved = change(client,root,source,'attributes',value)
        assert saved['metadata']['attributes'] == value
        fetched = client.get('/api/assistant/note',params={'path':saved['path']})
        assert fetched.status_code == 200 and fetched.json()['metadata']['attributes'] == value
    for row in records.records(root):
        original = before[row['id']]
        for key in ('body','id','created','parent','custom'):
            assert row.get(key) == original.get(key)
    listing = client.get('/api/assistant').json()['documents']
    guide = next(row for row in listing if row['id'] == note.stem)
    assert guide['attributes'] == value and guide['tab_attributes'] == [value,value]
    change(client,root,content,'attributes',{})
    change(client,root,note,'attributes',None)
    assert records.resolve(root,note.stem)[1]['attributes'] is None
    assert records.resolve(root,str(content.relative_to(root)))[1]['attributes'] == {}
    assert records.resolve(root,str(work.relative_to(root)))[1]['attributes'] == value
    assert records.verify(root)['valid']


def test_attribute_updates_reject_stale_and_type_mismatched_values(client, library):
    root, _, note, *_ = library
    change(client,root,note,'attributes',{'is_RFC':True})
    path = str(note.relative_to(root))
    original = note.read_bytes()
    for expected in [None,{}, {'is_RFC':1}, {'is_RFC':False}]:
        stale = client.patch('/api/assistant/metadata',json={
            'path':path,'field':'attributes','value':{'new':True},'expected':expected})
        assert stale.status_code == 409, stale.text
        assert note.read_bytes() == original


def test_numeric_attributes_accept_browser_number_round_trips(client, library):
    root, _, note, *_ = library
    change(client,root,note,'attributes',{'score':2.0,'nested':[{'score':1.0,'flag':True}]})
    expected = {'score':2,'nested':[{'score':1,'flag':True}]}
    response = client.patch('/api/assistant/metadata',json={
        'path':str(note.relative_to(root)),'field':'attributes','value':{'score':3},'expected':expected})
    assert response.status_code == 200,response.text
    assert not attributes.equal({'nested':[True]}, {'nested':[1]})


@pytest.mark.parametrize('value',['true',True,[], {'':True}, {'a'*101:True}, {'x':'a'*4097},
                                 {'x':list(range(101))}, {str(i):'x'*4096 for i in range(9)}])
def test_invalid_attributes_cannot_write(client, library, value):
    root, _, note, *_ = library
    original = note.read_bytes()
    response = client.patch('/api/assistant/metadata',json={
        'path':str(note.relative_to(root)),'field':'attributes','value':value,'expected':None})
    assert response.status_code in (400,422),response.text
    assert note.read_bytes() == original


def test_non_json_and_deep_attribute_values_are_rejected():
    value = {'a':True}
    for _ in range(9): value = {'nested':value}
    for invalid in (value,{'x':float('nan')},{'x':float('inf')},{'x':set()}, {1:'x'}):
        with pytest.raises(ValueError): attributes.validate(invalid)


def test_attributes_do_not_make_other_metadata_accept_objects(client, library):
    root, _, note, *_ = library
    original = note.read_bytes()
    response = client.patch('/api/assistant/metadata',json={
        'path':str(note.relative_to(root)),'field':'title','value':{'title':'Wrong'},'expected':'Guide'})
    assert response.status_code == 400 and note.read_bytes() == original


def test_attribute_filters_save_with_nested_boolean_logic(client, library):
    root, *_ = library
    first = dashboard.read(root)
    section = {**first['section_template'],'id':'rfc','title':'RFCs',
               'where':"source = 'active' AND (is_RFC = true OR any_tab.tags CONTAINS 'research' OR outcome IS MISSING)"}
    saved = client.put('/api/assistant/dashboard',json={'sections':[section],'expected':first['revision']})
    assert saved.status_code == 200,saved.text
    assert client.get('/api/assistant').json()['dashboard']['sections'] == [section]


@pytest.mark.parametrize('condition',[
    True, {}, {'name':'flag'}, {'name':'flag','equals':True,'exists':True},
    {'name':'flag','equals':True,'extra':False}, {'name':'flag','exists':'true'},
    {'name':'','equals':True}, {'name':'x'*101,'equals':True},
    {'name':'flag','equals':True,'scope':'series'}, {'name':'flag','equals':True,'scope':[]},
])
def test_invalid_attribute_filter_is_rejected(condition):
    with pytest.raises(ValueError): dashboard.validate_filter({'attribute':condition})
