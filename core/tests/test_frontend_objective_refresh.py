"""Objective polling sees external changes without repainting unchanged views."""
from .test_frontend_terminal_ui import _run_node
from .test_frontend_objective_terminal_order import SOURCE


def test_current_objective_polling_is_scoped_nonoverlapping_and_change_driven():
    source = SOURCE.read_text()
    helpers = source[source.index('  async function load('):source.index('  function notify(')]
    result = _run_node(r'''
const cache=new Map(),pending=new Map(),queues=new Map(),overlays=new Map(),loadedAt=new Map();
let scope={workspace_id:'one',vault:'vault',path:'/one'},refreshTimer,openView={type:'tasks'};
const key=s=>(s?.vault||'')+'::'+s?.workspace_id,context=()=>scope,data=()=>cache.get(key(scope));
const events={},document={hidden:false,addEventListener:(name,fn)=>events[name]=fn};
window.addEventListener=(name,fn)=>events[name]=fn;
let tick,interval,paints=0,sidebar=0,terminals=0,tasks=0,requests=[],release;
const setInterval=(fn,ms)=>{tick=fn;interval=ms;return 1;};
const paint=()=>paints++,renderTasks=()=>tasks++,renderOverview=()=>{},paintLibrary=()=>{};
const bridge={refreshSidebar:()=>sidebar++,refreshTerminals:()=>terminals++};
const notices=[],notify=message=>notices.push(message);
let payload={enabled:true,revision:'same',objectives:[{id:'objective',resources:[{content:{body:'old'}}]}]};
const fetch=async url=>{requests.push(url);if(release===true)await new Promise(r=>release=r);return {ok:true,json:async()=>structuredClone(payload)};};
cache.set(key(scope),structuredClone(payload));
''' + helpers + r'''
(async()=>{
 startRefreshing();startRefreshing();tick();await pending.get(key(scope));await refreshCurrent();
 const unchanged={paints,sidebar,terminals,tasks};
 payload.objectives[0].resources[0].content.body='externally changed';await refreshCurrent();
 const changed={paints,sidebar,terminals,tasks};
 queues.set(key(scope),Promise.resolve());const beforeBusy=requests.length;await refreshCurrent();queues.clear();
 document.hidden=true;await refreshCurrent();document.hidden=false;
 const skipped=requests.length===beforeBusy;
 release=true;const running=refreshCurrent(),beforeOverlap=requests.length;await refreshCurrent();
 const nonoverlap=requests.length===beforeOverlap;
 scope={workspace_id:'two',vault:'vault',path:'/two'};release();release=null;await running;
 const afterSwitch={paints,sidebar,terminals,tasks};await refreshCurrent();
 scope={workspace_id:'one',vault:'vault',path:'/one'};payload.revision='new';events.focus();await pending.get(key(scope));
 release=true;const oldRead=refreshCurrent();cache.set(key(scope),{...payload,revision:'saved-after-read'});release();release=null;await oldRead;
 console.log(JSON.stringify({interval,unchanged,changed,afterSwitch,skipped,nonoverlap,
 requests,notices,latest:cache.get(key(scope)).revision}));
})().catch(e=>{console.error(e);process.exit(1)});
''')
    assert result['interval'] == 5000
    assert result['unchanged'] == {'paints': 0, 'sidebar': 0, 'terminals': 0, 'tasks': 0}
    assert result['changed'] == result['afterSwitch'] == {'paints': 1, 'sidebar': 1, 'terminals': 1, 'tasks': 1}
    assert result['skipped'] and result['nonoverlap']
    assert all('workspace_id=one' in url for url in result['requests'])
    assert result['latest'] == 'saved-after-read' and result['notices'] == []
