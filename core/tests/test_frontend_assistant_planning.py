from .test_frontend_terminal_ui import _run_node
from .test_frontend_assistant import ASSISTANT_APP


def test_planning_views_keep_deadlines_and_created_dates_distinct():
    source = ASSISTANT_APP.read_text()
    helpers = source[source.index('  const e ='):source.index('  function countWhere(')]
    result = _run_node('''
const state = {data:{tasks:[]}, view:'all_open', status:'', priority:'', workspace:'demo', search:''};
''' + helpers + '''
const today = localToday();
const future = new Date(); future.setDate(future.getDate() + 40);
const later = localToday(future);
state.data.tasks = [
 {path:'planned', title:'Planned', workspace:'demo', status:'ready', scheduled:today, created:'2026-09-14T00:10:00+14:00'},
 {path:'bill', title:'Bill', workspace:'demo', status:'ready', due:today, defer_until:later, recurrence:'monthly', created:'2026-09-14T23:50:00-11:00'},
 {path:'deferred', title:'Deferred', workspace:'demo', status:'ready', scheduled:today, defer_until:later, created:'2026-09-13'},
 {path:'unknown', title:'Unknown', workspace:'demo', status:'inbox', recurrence:'monthly'},
 {path:'someday', title:'Someday', workspace:'demo', status:'ready', priority:'P3'},
 {path:'waiting', title:'Waiting', workspace:'demo', status:'waiting', follow_up_at:later},
 {path:'done', title:'Done', workspace:'demo', status:'done', scheduled:today, completed:today},
 {path:'other', title:'Other', workspace:'other', status:'ready', scheduled:today}
];
const dataBefore=JSON.stringify(state.data);
const views = {};
for (const view of ['today','week','recurring','someday','waiting','recent']) {
 state.view=view; views[view]=filteredTasks().map(row=>row.path).sort();
}
const grouped=dateGroups(state.data.tasks.slice(0,4), row=>`<b>${e(row.title)}</b>`, row=>taskCreatedDate(row.created), 'task');
console.log(JSON.stringify({views, grouped, unchanged:dataBefore===JSON.stringify(state.data),
 invalid:taskCreatedDate('2026-02-30T12:00:00Z')}));
''')
    assert result['views']['today'] == ['bill', 'planned']
    assert result['views']['week'] == ['bill', 'planned']
    assert result['views']['recurring'] == ['bill', 'unknown']
    assert result['views']['someday'] == ['bill', 'deferred', 'someday']
    assert result['views']['waiting'] == ['waiting']
    assert result['views']['recent'] == ['done']
    assert result['grouped'].count('data-assistant-task-date="2026-09-14"') == 1
    assert result['grouped'].index('2026-09-14') < result['grouped'].index('2026-09-13') < result['grouped'].index('Undated')
    assert result['unchanged'] and result['invalid'] == ''


def test_switching_to_meetings_clears_task_filters_and_late_refresh_hints():
    source = ASSISTANT_APP.read_text()
    helpers = source[source.index('  const e ='):source.index('  function progressLabel(')]
    lifecycle = source[source.index('  async function refresh('):source.index("  document.addEventListener('keydown'")]
    result = _run_node('''
const data={configured:true, exists:true, root:'/fixture', workspaces:[{id:'demo'},{id:'other'}],
 tasks:[{path:'task.md', workspace:'demo'}], meetings:[{path:'one',workspace:'demo'},{path:'two',workspace:'other'}]};
const state={data,section:'tasks',workspace:'demo',search:'Task',view:'all_open',selectedTaskPath:'task.md',request:0,poll:1};
let location=new URL('https://lab.example/?view=assistant&assistant_workspace=demo');
const window={get location(){return location;}};
const history={pushState(a,b,url){location=new URL(url,location);}};
const document={body:{classList:{contains:()=>true}},querySelectorAll:()=>[],getElementById:()=>null};
const fetch=async url=>({ok:true,json:async()=>url==='/api/assistant'?data:[]});
function render(){} function closeDocumentModal(){} function workspaceRows(){return data.workspaces;}
''' + helpers + lifecycle + '''
(async()=>{
 const pending=refresh({task:'task.md',workspace:'demo'});
 setSection('meetings'); await pending;
 const entered={workspace:state.workspace,search:state.search,count:filteredMeetings().length,url:location.searchParams.get('assistant_workspace')};
 state.workspace='other'; await refresh(); const filtered=filteredMeetings().map(row=>row.path);
 init({section:'meetings',workspace:'demo',task:'task.md'}); await refresh();
 console.log(JSON.stringify({entered,filtered,reloaded:filteredMeetings().length}));
})();
''')
    assert result['entered'] == {'workspace':'','search':'','count':2,'url':None}
    assert result['filtered'] == ['two']
    assert result['reloaded'] == 2
