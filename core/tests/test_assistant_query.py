"""SQL-style filters parse once on the server and retain browser semantics."""
import json

import pytest
from lab import assistant_query as query, assistant_dashboard as dashboard
from .test_assistant_documents_unified import library
from .test_frontend_assistant import ASSISTANT_APP
from .test_frontend_terminal_ui import _run_node


def test_precedence_quotes_values_and_scopes():
    result = query.parse("WHERE is_RFC = true OR score >= 2 AND NOT stage IN ('Draft', 'Won''t do')")
    assert set(result) == {'or'} and set(result['or'][1]) == {'and'}
    assert result['or'][1]['and'][1]['not']['compare']['values'][1] == {'literal':"Won't do"}
    quoted = query.parse('any_tab."flag with spaces" = true')['compare']['field']
    assert quoted == {'scope':'any_tab','name':'flag with spaces'}
    assert query.parse('attributes.title = false')['compare']['field']['scope'] == 'document'
    assert query.parse('due <= CURRENT_DATE() - 2')['compare']['value'] == {'today':-2}
    assert query.parse("data = JSON '{\"ok\":true}'")['compare']['value'] == {'json':{'ok':True}}


@pytest.mark.parametrize('text',[
    '', 'source =', "source = 'invalid'", 'kind > 2', "source LIKE 'open'", 'source = true',
    "title = 'unterminated", 'score IN ()', 'score IN (1,)', 'score BETWEEN 1 2',
    'due <= TODAY + 1.5', 'due <= TODAY + 36501', 'score > 1e999', 'NOT '*18+'is_RFC',
    '(' * 18 + 'is_RFC' + ')' * 18, 'is_RFC IS true', 'stage LIKE 4', 'anything.name = true',
    'score = 2; DROP TABLE notes', "__import__('os')", "SELECT * FROM notes", 'true -- comment',
    "flag = JSON '{bad}'", ' AND '.join(['is_RFC = true']*101),
])
def test_invalid_queries_are_rejected_with_useful_errors(text):
    with pytest.raises(ValueError): query.parse(text)


def test_sql_sections_validate_save_and_reject_invalid_drafts(client, library):
    root, *_ = library
    first = dashboard.read(root)
    section = {**first['section_template'],'id':'research','title':'Research',
               'where':"source = 'open' AND (is_RFC = true OR is_investigation = true)"}
    saved = client.put('/api/assistant/dashboard',json={'sections':[section],'expected':first['revision']})
    assert saved.status_code == 200,saved.text
    assert saved.json()['compiled_filters']['research'] == query.parse(section['where'])
    stored = root/'.assistant/dashboard/research.json'
    assert json.loads(stored.read_text()) == section and 'compiled_filters' not in stored.read_text()
    before = stored.read_bytes()
    for where in ('priority =',"source = 'bad'",False,{}):
        response = client.put('/api/assistant/dashboard',json={
            'sections':[{**section,'where':where}],'expected':saved.json()['revision']})
        assert response.status_code == 400,response.text
        assert stored.read_bytes() == before


def test_existing_json_expressions_migrate_with_original_backup(library):
    root, *_ = library
    old = {'schema':2,'id':'focus','title':'Focus','position':-10,'sort':'due','limit':20,
           'filter':{'and':[{'source':'open'},{'or':[{'priority':['P0']},{'due':{'within_days':2,'include_overdue':True}}]},
                            {'attribute':{'name':'is_RFC','equals':True}}]}}
    folder = root/'.assistant/dashboard';folder.mkdir()
    source = folder/'focus.json';source.write_text(json.dumps(old,indent=2))
    before = source.read_bytes()
    projected = dashboard.read(root)
    assert projected['sections'][0]['where'] == "source = 'open' AND (priority IN ('P0') OR due <= TODAY + 2) AND attributes.is_RFC = true"
    assert source.read_bytes() == before
    saved = dashboard.migrate(root)
    assert saved == projected and json.loads(source.read_text()) == projected['sections'][0]
    backups = list((root/'.assistant/backups').glob('dashboard-schema-2-*/focus.json'))
    assert len(backups) == 1 and backups[0].read_bytes() == before
    assert dashboard.migrate(root) == saved


def test_browser_sql_predicates_and_legacy_equivalence():
    source = ASSISTANT_APP.read_text()
    helpers = source[source.index('  const e ='):source.index('  function countWhere(')]
    matching = source[source.index('  function pendingWork'):source.index('  function dashboardSections')]
    cases = {
        'source_open':("source = 'open'",True),
        'precedence':("is_RFC = true OR is_investigation = true AND score < 0",True),
        'grouping':("(is_RFC = true OR is_investigation = true) AND score < 0",False),
        'not':("NOT is_investigation = true",True),
        'typed':("is_RFC = 1",False),
        'in':("stage IN ('Review', 'Draft')",True),
        'not_in':("stage NOT IN ('Review', 'Draft')",False),
        'number':('score >= 2 AND score < 3',True),
        'contains':("tags CONTAINS 'research'",True),
        'like':("title LIKE 'RFC _%'",True),
        'literal_regex':("title LIKE '[RFC]'",False),
        'missing':('unset IS MISSING',True),
        'null':('outcome IS NULL AND outcome IS NOT MISSING',True),
        'not_null':('is_RFC IS NOT NULL',True),
        'unknown_ne':('unset != true',False),
        'unknown_not':('NOT unset = true',False),
        'unknown_or':('unset = true OR is_RFC = true',True),
        'unknown_and':('unset = true AND is_RFC = true',False),
        'any_tab':('any_tab.child_flag = true',True),
        'root_scope':('child_flag = true',False),
        'custom_reserved':("attributes.title = 'Custom'",True),
        'json_null':("outcome = JSON 'null'",True),
        'json_object':("data = JSON '{\"ok\":true}'",True),
        'due_soon':('due <= TODAY + 2',True),
        'due_window':('due BETWEEN TODAY AND TODAY + 2',False),
        'quoted_name':('"is RFC" = true',True),
    }
    legacy = [
        {'source':'open'}, {'starred':False}, {'priority':['P1']},
        {'due':{'within_days':2,'include_overdue':True}},
        {'due':{'within_days':2,'include_overdue':False}},
        {'attribute':{'name':'outcome','equals':None}},
        {'attribute':{'name':'missing','equals':False}},
        {'attribute':{'name':'tags','contains':None}},
        {'attribute':{'name':'data','equals':{'ok':True}}},
        {'attribute':{'name':'is_RFC','exists':True}},
        {'attribute':{'name':'missing','exists':False,'scope':'any_tab'}},
        {'attribute':{'name':'title','equals':'Custom'}},
        {'attribute':{'name':'is_investigation','equals':False}},
        {'search':'rfc'},
    ]
    compiled = {name:query.parse(text) for name,(text,_) in cases.items()}
    pairs = [[node,query.parse(query.from_filter(node))] for node in legacy]
    result = _run_node('const state={data:{documents:[]}};const compiled='+json.dumps(compiled)+';const pairs='+json.dumps(pairs)+';' + helpers + matching + '''
const relative=days=>{const date=new Date();date.setDate(date.getDate()+days);return localToday(date)};
const row={path:'rfc',id:'rfc',title:'RFC A',tracked:true,keep_in_documents:true,status:'not_started',priority:'P1',attributes:{is_RFC:true,is_investigation:false,score:2.5,stage:'Review',title:'Custom',tags:['research',null],outcome:null,data:{ok:true},'is RFC':true},tab_attributes:[{child_flag:true}],subtasks:[{id:'overdue',status:'not_started',due:relative(-1),priority:'P1'},{id:'far',status:'not_started',due:relative(4)}]};
state.data.documents=[row];
console.log(JSON.stringify({cases:Object.fromEntries(Object.entries(compiled).map(([name,filter])=>[name,dashboardMatches(row,{filter})])),equivalent:pairs.every(([old,sql])=>dashboardMatches(row,{filter:old})===dashboardMatches(row,{filter:sql}))}));
''')
    assert result['cases'] == {name:expected for name,(_,expected) in cases.items()}
    assert result['equivalent']
