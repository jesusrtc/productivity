"""Filtering groups series without losing old pending work or date boundaries."""
import json
from lab import assistant_dashboard, assistant_query
from .test_frontend_terminal_ui import _run_node
from .test_frontend_assistant import ASSISTANT_APP


def test_dashboard_series_and_deadline_filters():
    source = ASSISTANT_APP.read_text()
    helpers = source[source.index('  const e ='):source.index('  function countWhere(')]
    dashboard = source[source.index('  function pendingWork'):source.index('  function renderDashboard')]
    filters = source[source.index('  function documentKind'):source.index('  function starButton')]
    defaults = [json.loads(path.read_text()) for path in sorted((assistant_dashboard.RESOURCES/'dashboard').glob('*.json'))]
    compiled={row['id']:assistant_query.parse(row['where']) for row in defaults}
    result = _run_node('const compiledFilters='+json.dumps(compiled)+';const dashboardDefaults=' + json.dumps(defaults) + ';\n' + '''
const state={view:'dashboard',search:'',data:{documents:[],dashboard:{sections:dashboardDefaults,compiled_filters:compiledFilters}}};
''' + helpers + dashboard + filters + '''
const relative=days=>{const date=new Date();date.setDate(date.getDate()+days);return localToday(date)};
const task=(path,props={})=>({path,id:path,title:path,type:'task',tracked:true,status:'not_started',priority:'P2',...props});
const series={path:'series',id:'s',title:'Weekly meeting',type:'note',note_type:'series',keep_in_documents:true,starred:true};
const older=task('older',{type:'note',note_type:'meeting',date:'2026-01-01',series:'s',priority:'P1',starred:true,keep_in_documents:true});
const latest={path:'latest',id:'latest',title:'Latest meeting',note_type:'meeting',type:'note',date:'2026-01-08',series:'s',keep_in_documents:true};
const undated={path:'undated',id:'undated',title:'Undated',note_type:'meeting',type:'note',created:'2030-01-01',series:'s',keep_in_documents:true};
state.data.documents=[series,older,latest,undated,task('p1',{priority:'P1'}),task('today',{due:relative(0)}),task('two',{due:relative(2)}),task('three',{due:relative(3)}),task('overdue',{due:relative(-1)}),task('done',{status:'done',priority:'P1',due:relative(0)}),task('child',{subtasks:[{id:'childwork',status:'not_started',priority:'P1'}]}),task('skipped',{subtasks:[{id:'branch',status:'skipped'},{id:'grandchild',parent:{id:'branch'},priority:'P1',due:relative(0)}]}),task('donechild',{subtasks:[{id:'completed',status:'done',priority:'P1',due:relative(0)}]})];
const before=JSON.stringify(state.data);
const section=dashboardDefaults.find(row=>row.id==='priority');
const matches=state.data.documents.filter(row=>dashboardMatches(row,section)).map(row=>row.path).sort();
const grouped=collapseSeries(state.data.documents);
const priority=dashboardSections()[0].rows;
const sections=dashboardSections();
const seriesSections=sections.filter(section=>section.rows.some(row=>row.displayKey==='series:s')).map(section=>section.id);
const filtered=collapseSeries([older]);
const dueOnly={...section,filter:{due:{within_days:2,include_overdue:false}}};
const and={...section,filter:{and:[{priority:['P1']},{due:{within_days:2,include_overdue:true}}]}};
const result={matches,grouped:grouped.filter(row=>row.displaySeries).map(row=>[row.path,row.displayKey,row.seriesMembers.length]),
 priority:priority.map(row=>row.path),unique:sections.every(section=>new Set(section.rows.map(row=>row.displayKey)).size===section.rows.length),seriesSections,
 latestForOlder:filtered[0].path,unchanged:before===JSON.stringify(state.data),
 noOverdue:!dashboardMatches(state.data.documents.find(row=>row.path==='overdue'),dueOnly),
 andRejects:!dashboardMatches(older,and),twoIncluded:dashboardMatches(state.data.documents.find(row=>row.path==='two'),dueOnly)};
state.data.dashboard={sections:[]};result.empty=dashboardSections().length;
console.log(JSON.stringify(result));
''')
    assert result['matches'] == ['child','older','overdue','p1','today','two']
    assert result['grouped'] == [['latest','series:s',3]]
    assert 'latest' in result['priority'] and 'older' not in result['priority']
    assert result['latestForOlder'] == 'latest'
    assert result['seriesSections'] == ['priority','starred','documents']
    assert all(result[field] for field in ['unique','unchanged','noOverdue','andRejects','twoIncluded'])
    assert result['empty'] == 0


def test_sections_keep_independent_membership_limits_and_exclusions():
    source=ASSISTANT_APP.read_text()
    helpers=source[source.index('  const e ='):source.index('  function countWhere(')]
    dashboard=source[source.index('  function pendingWork'):source.index('  function renderDashboard')]
    filters=source[source.index('  function documentKind'):source.index('  function starButton')]
    queries={'starred':"starred = true",'documents':"source = 'active'",'exclude':"source = 'active' AND starred = false"}
    compiled={name:assistant_query.parse(query) for name,query in queries.items()}
    result=_run_node('const compiled='+json.dumps(compiled)+';' + '''
const state={view:'dashboard',search:'',data:{documents:[],dashboard:{compiled_filters:compiled,sections:[]}}};
''' + helpers + dashboard + filters + '''
state.data.documents=[{path:'a',id:'a',title:'A',starred:true,keep_in_documents:true},{path:'b',id:'b',title:'B',starred:true,keep_in_documents:true},{path:'c',id:'c',title:'C',starred:false,keep_in_documents:true}];
const sections=state.data.dashboard.sections=[{id:'starred',position:0,sort:'title',limit:1},{id:'documents',position:10,sort:'title',limit:0}];
const memberships=()=>Object.fromEntries(dashboardSections().map(section=>[section.id,{rows:section.rows.map(row=>row.path),total:section.total}]));
const limited=memberships();sections[0].position=20;
const reordered=memberships();sections[0].limit=0;
const unlimited=memberships();compiled.documents=compiled.exclude;
const excluded=memberships();
console.log(JSON.stringify({limited,reordered,unlimited,excluded}));
''')
    assert result['limited'] == result['reordered'] == {
        'starred':{'rows':['a'],'total':2},'documents':{'rows':['a','b','c'],'total':3}}
    assert result['unlimited']['starred'] == {'rows':['a','b'],'total':2}
    assert result['unlimited']['documents'] == {'rows':['a','b','c'],'total':3}
    assert result['excluded']['documents'] == {'rows':['c'],'total':1}
    assert result['excluded']['starred'] == result['unlimited']['starred']


def test_explicit_boolean_groups_and_readable_json_round_trip():
    source=ASSISTANT_APP.read_text()
    helpers=source[source.index('  const e ='):source.index('  function countWhere(')]
    matching=source[source.index('  function pendingWork'):source.index('  function dashboardSections')]
    formatter=source[source.index('  function formatSectionJson'):source.index('  function editDashboardSection')]
    result=_run_node('''const state={data:{documents:[]}};''' + helpers + matching + formatter + '''
const row={id:'one',path:'one',title:'A \"quoted\" title',tracked:true,status:'not_started',priority:'P1',workspace:'team-a',project:'x',starred:false,type:'task'};
state.data.documents=[row];
const a={priority:['P1']},b={workspace:'team-b'},c={project:'x'};
const grouped={filter:{and:[{or:[a,b]},c]}};
const formatted=formatSectionJson({schema:2,id:'test',title:'Quotes " and newline\\n',position:0,filter:grouped.filter,sort:'title',limit:20});
const series={id:'series',path:'series',note_type:'series',starred:false};
const older={id:'old',path:'old',series:'series',starred:true};
const latest={id:'new',path:'new',series:'series',starred:false};
state.data.documents.push(series,older,latest);
console.log(JSON.stringify({
 or:dashboardMatches(row,{filter:{or:[a,b]}}),and:dashboardMatches(row,{filter:{and:[a,b]}}),
 nested:dashboardMatches(row,grouped),negative:dashboardMatches(row,{filter:{starred:false}}),
 groupStarred:dashboardMatches(latest,{filter:{starred:true}}),groupUnstarred:dashboardMatches(latest,{filter:{starred:false}}),
 valid:JSON.parse(formatted).filter,formatted
}));
''')
    assert result['or'] and not result['and'] and result['nested'] and result['negative']
    assert result['groupStarred'] and not result['groupUnstarred']
    assert result['valid']=={'and':[{'or':[{'priority':['P1']},{'workspace':'team-b'}]},{'project':'x'}]}
    assert '{ "priority": ["P1"] }' in result['formatted']


def test_custom_attributes_use_explicit_types_scopes_and_groups():
    source=ASSISTANT_APP.read_text()
    helpers=source[source.index('  const e ='):source.index('  function countWhere(')]
    matching=source[source.index('  function pendingWork'):source.index('  function dashboardSections')]
    result=_run_node('const state={data:{documents:[]}};' + helpers + matching + '''
const row={id:'rfc',path:'rfc',attributes:{is_RFC:true,is_investigation:false,stage:'Design review',tags:['one','two'],result:null,details:{ok:true,n:2}},tab_attributes:[{child_flag:true}],tracked:true,status:'not_started'};
const check=attribute=>dashboardMatches(row,{filter:{attribute}});
const series={id:'s',path:'series',note_type:'series'};
const older={id:'old',path:'old',series:'s',date:'2026-01-01',attributes:{is_RFC:true}};
const latest={id:'new',path:'new',series:'s',date:'2026-01-08'};
state.data.documents=[row,series,older,latest];
console.log(JSON.stringify({
 boolean:check({name:'is_RFC',equals:true}),wrongType:check({name:'is_RFC',equals:1}),
 caseSensitive:check({name:'is_rfc',equals:true}),false:check({name:'is_investigation',equals:false}),
 missingFalse:check({name:'missing',equals:false}),missingNull:check({name:'missing',equals:null}),
 null:check({name:'result',equals:null}),presentNull:check({name:'result',exists:true}),
 absent:check({name:'missing',exists:false}),prototype:check({name:'toString',exists:true}),
 array:check({name:'tags',contains:'two'}),substring:check({name:'stage',contains:'review'}),
 nested:check({name:'details',equals:{n:2,ok:true}}),nestedType:check({name:'details',equals:{n:2,ok:1}}),
 rootOnly:check({name:'child_flag',equals:true}),anyTab:check({name:'child_flag',equals:true,scope:'any_tab'}),
 and:dashboardMatches(row,{filter:{and:[{attribute:{name:'is_RFC',equals:true}},{attribute:{name:'is_investigation',equals:true}}]}}),
 or:dashboardMatches(row,{filter:{or:[{attribute:{name:'is_RFC',equals:true}},{attribute:{name:'is_investigation',equals:true}}]}}),
 series:collapseSeries(state.data.documents.filter(r=>dashboardMatches(r,{filter:{attribute:{name:'is_RFC',equals:true}}}))).map(r=>r.path)
}));
''')
    for key in ('boolean','false','null','presentNull','absent','array','substring','nested','anyTab','or'):
        assert result[key],key
    for key in ('wrongType','caseSensitive','missingFalse','missingNull','prototype','nestedType','rootOnly','and'):
        assert not result[key],key
    assert result['series'] == ['rfc','new']
