"""Terminal hierarchy and Objective folding preserve live session identities."""
import functools
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import shutil
import subprocess
from threading import Thread
import time

import pytest

from .test_frontend_terminal_ui import _js_between, _run_node, LAB_APP, LAB_SHELL_CSS


GROUPS = _js_between('  function _termGroupScopeKey()', '  function _termSessionDisplay(s)')
MOVES = _js_between('  function _termPlanItemMove(', '  function termReorderSessions(')
RENDER = _js_between('  function _termTaskPlaceholderHtml(', '  // One move plan')
PILL = _js_between('  function _termTaskStatusLabel(', '  function _termMarkVisibleCompletionSeen(')
ASSOCIATION = _js_between('  function _termSessionAssociationHtml(', '  function _termTaskStatusLabel(')
ALL_TOGGLE = _js_between('  function termSetWipOnly(', '  function termSetRecentEnabled(')
OBJECTIVE_ACTIVATE = _js_between('  function _termActivateObjectiveTerminal(', '  async function _termActivateTab(')
OBJECTIVES = LAB_APP.parent / 'lib/workspace-objectives.js'


def test_task_terminal_rows_inherit_context_reuse_primaries_and_preserve_manual_layout():
    source = OBJECTIVES.read_text()
    helpers = source[source.index('  function terminalIdentity('):source.index('  function sidebarTarget(')]
    result = _run_node(r'''
const _TERM_GROUP_COLORS=['#58a6ff'];
const task=(id,children=[])=>({id,title:id,children});
const o={id:'one',name:'Project',tasks:[task('parent',[task('subtask')]),task('missing')],resources:[],worktrees:[]};
const registry={enabled:true,focused:['one'],objectives:[o],terminal_links:{
 global:{objective_id:'one'},parent:{objective_id:'one',task_id:'parent'},subtask:{objective_id:'one',task_id:'subtask'},
 extra:{objective_id:'one',view:'tasks'},grandchild:{objective_id:'one',view:'tasks'}}};
const termSessions=['global','parent','subtask','extra','grandchild'].map(name=>({name,logical_name:name,session_id:name}));
let termCurrentSession='grandchild',selected=null,current=o;
const data=()=>registry,context=()=>({workspace_id:'work',vault:'fixture',path:'/workspace'}),active=()=>true,objective=()=>current;
const tasks=o=>o?.tasks.flatMap(t=>[t,...t.children])||[],taskIcon=()=>'<icon>',customTaskIcon=()=>'',taskStatus=()=> 'todo',taskDisplayName=t=>t.title,esc=String;
const key=s=>(s?.vault||'')+'::'+s?.workspace_id;
const view={tree:{}},state=()=>view,persistView=()=>{},paint=()=>{},scopeRows=()=>[];
const opened=[],created=[],activated=[];
const focusedTask=()=>tasks(current).find(task=>task.id===selected);
const openTask=id=>{selected=id;opened.push(id);};
const selectObjective=id=>{current=registry.objectives.find(o=>o.id===id);selected=null;};
const terminalLaunchContext=()=>({id:current.id,path:'/workspace/objectives/one',context:{...context()}});
let finishCreate;
const bridge={parentTerminal:t=>termSessions.find(p=>p.logical_name===_termSubtabParents(group,termSessions)[t.logical_name]),
 sessions:()=>termSessions,activateLinkedTerminal:ids=>activated.push(ids),
 createTaskTerminal:(launch,task)=>{created.push({launch,task});return new Promise(r=>finishCreate=r);}};
''' + helpers + GROUPS + r'''
const group=_termNormalizeGroupState({order:termSessions.map(t=>'s:'+t.name),tabParents:{extra:'subtask',grandchild:'extra'}});
window.LabObjectives={terminalParents,terminalExpanded,terminalMain,sameTerminalObjective:(a,b)=>terminalObjective(a)?.id===terminalObjective(b)?.id};
const augmented=terminalSessions(termSessions,{wipOnly:false}),parents=_termSubtabParents(group,augmented);
const missing=augmented.find(t=>t.task_id==='missing'),binding=terminalTask(termSessions[4]);
const original=JSON.stringify(registry.terminal_links);
openForTerminal(termSessions[4]);const expanded=terminalExpanded(termSessions[1]);
''' + MOVES + r'''
const fixedMove=_termPlanItemMove(group,'s:subtask','s:global',false,'','below');
const moved=_termPlanItemMove(group,'s:subtask',null,false,'','below');
(async()=>{
 await openTaskTerminal('parent');await openTaskTerminal(null);
 const first=openTaskTerminal('missing'),second=openTaskTerminal('missing');
 finishCreate({name:'new-terminal'});await Promise.all([first,second]);
 console.log(JSON.stringify({parents,missing,binding:{id:binding.task.id,inherited:binding.inherited},expanded,
 opened,created,activated,fixedMove,manualParents:_termSubtabParents(moved,augmented),manualRoots:moved.tabRoots,
 ownTask:taskForTerminal(termSessions[1]),extraTask:taskForTerminal(termSessions[4]),unchanged:original===JSON.stringify(registry.terminal_links)}));
})().catch(e=>{console.error(e);process.exit(1)});
''')
    assert result['parents'] == {'subtask': 'parent', 'extra': 'subtask', 'grandchild': 'extra'}
    assert result['missing']['objective_placeholder'] and result['missing']['label'] == 'missing'
    assert result['binding'] == {'id': 'subtask', 'inherited': True}
    assert result['expanded'] and result['opened'][0] == 'subtask'
    assert result['ownTask']['title'] == 'parent' and not result['ownTask']['inherited']
    assert result['extraTask']['title'] == 'subtask' and result['extraTask']['inherited']
    assert result['activated'] == [['parent'], ['global'], ['new-terminal']]
    assert len(result['created']) == 1 and result['created'][0]['task']['id'] == 'missing'
    assert result['fixedMove'] is None
    assert result['manualRoots'] == ['subtask']
    assert result['manualParents'] == {'extra': 'subtask', 'grandchild': 'extra'}
    assert result['unchanged']


def test_subtab_moves_keep_descendants_reject_cycles_and_scope_and_promote_orphans():
    result = _run_node(r'''
const _TERM_GROUP_COLORS=['#58a6ff'];
const termSessions=['a','b','c','d','other'].map(name=>({name,logical_name:name,objective:name==='other'?'two':'one'}));
let termCurrentSession='a';
const termSessEsc=String,_termSessionDisplay=s=>s.name;
window.LabObjectives={sameTerminalObjective:(a,b)=>a?.objective===b?.objective};
''' + GROUPS + MOVES + r'''
const original=_termNormalizeGroupState({order:['s:a','s:b','s:c','s:d','s:other'],tabParents:{c:'b'}});
const before=JSON.stringify(original);
const nested=_termPlanItemMove(original,'s:b','s:a',false,'','child');
const sibling=_termPlanItemMove(nested,'s:b','s:a',false,'','below');
const render=_termSubtabRenderer(nested,termSessions,(s,i)=>`<span role="tab"><span class="sess-icon"></span>${s.name}</span>`);
const html=termSessions.map(render).join('');
const activeHtml=(()=>{termCurrentSession='c';return termSessions.map(_termSubtabRenderer(nested,termSessions,(s,i)=>`<span role="tab"><span class="sess-icon"></span>${s.name}</span>`)).join('')})();
console.log(JSON.stringify({nested,sibling,html,activeHtml,unchanged:before===JSON.stringify(original),
 cycle:_termPlanItemMove(nested,'s:a','s:c',false,'','child'),
 foreign:_termPlanItemMove(nested,'s:b','s:other',false,'','child'),
 orphanParents:_termSubtabParents(nested,termSessions.filter(s=>s.name!=='b')),
 arranged:_termArrangeSubtabRows([termSessions[1],termSessions[2],termSessions[0],termSessions[3]],sibling).map(s=>s.name),
 normalized:_termNormalizeGroupState({tabParents:{a:'b',b:'a',self:'self'}}).tabParents}));
''')
    assert result['unchanged']
    assert result['nested']['tabParents'] == {'b': 'a', 'c': 'b'}
    assert result['nested']['order'] == ['s:a', 's:b', 's:c', 's:d', 's:other']
    assert result['sibling']['tabParents'] == {'c': 'b'}
    assert result['sibling']['tabAfter'] == {'b': 'a'}
    assert result['arranged'] == ['c', 'a', 'b', 'd']
    assert result['cycle'] is None and result['foreign'] is None
    assert result['orphanParents'] == {}
    assert result['normalized'] == {'b': 'a'}
    assert result['html'].count('data-term-parent=') == 2
    assert result['html'].count('data-subtab-hover-only hidden') == 2
    assert result['activeHtml'] == result['html']


def test_subtab_disclosure_requires_own_wip_task_and_always_folds_automation():
    result = _run_node(r'''
const _TERM_GROUP_COLORS=['#58a6ff'],termSessEsc=String,_termSessionDisplay=s=>s.name;
const automation='automation-'+('a'.repeat(32))+'-1';
const termSessions=['parent','wip','todo','done','paused','none','inherited',automation].map(name=>({name,logical_name:name}));
const bindings={wip:{status:'in_progress',inherited:false},todo:{status:'todo'},done:{status:'done'},paused:{status:'paused'},inherited:{status:'in_progress',inherited:true},[automation]:{status:'in_progress',inherited:false}};
window.LabObjectives={taskForTerminal:s=>bindings[s.name],terminalExpanded:()=>true};
''' + GROUPS + r'''
const state=_termNormalizeGroupState({tabParents:Object.fromEntries(termSessions.slice(1).map(s=>[s.name,'parent']))});
const html=termSessions.map(_termSubtabRenderer(state,termSessions,s=>`<span class="sess" role="tab" data-name="${s.name}">${s.name}</span>`)).join('');
console.log(JSON.stringify({html,automation}));
''')
    assert '<div class="term-subtab-node has-wip-child" data-term-parent="parent">' in result['html']
    assert 'data-name="wip" data-subtab-hover-only' not in result['html']
    for name in ('todo', 'done', 'paused', 'none', 'inherited', result['automation']):
        assert f'data-name="{name}" data-subtab-hover-only hidden' in result['html']


def test_nested_wip_paths_do_not_reveal_hover_only_ancestor_rows():
    result = _run_node(r'''
const _TERM_GROUP_COLORS=['#58a6ff'],termSessEsc=String,_termSessionDisplay=s=>s.name;
const termSessions=['parent','unassigned','working'].map(name=>({name,logical_name:name}));
window.LabObjectives={taskForTerminal:s=>s.name==='working'?{status:'in_progress',inherited:false}:null};
''' + GROUPS + r'''
const state=_termNormalizeGroupState({tabParents:{unassigned:'parent',working:'unassigned'}});
console.log(JSON.stringify({html:termSessions.map(_termSubtabRenderer(state,termSessions,s=>`<span class="sess" role="tab" data-name="${s.name}">${s.name}</span>`)).join('')}));
''')
    assert 'data-term-parent="unassigned" data-subtab-hover-parent>' in result['html']
    assert 'data-name="unassigned" data-subtab-hover-only hidden' in result['html']
    assert 'data-name="working" data-subtab-hover-only' not in result['html']
    assert result['html'].count(' hidden') == 1


@pytest.mark.parametrize('orientation', ['vertical', 'horizontal'])
def test_native_terminal_drop_choice_hover_reload_and_objective_folding(tmp_path, orientation):
    chrome = os.environ.get('CHROME_BIN') or shutil.which('chromium') or '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
    if not Path(chrome).is_file() or not shutil.which('node'):
        pytest.skip('Chrome and Node required')
    setup = r'''
let vault='fixture',workspace='demo',termCurrentSession='a',termCurrentWorkspaceId='demo';
let termSessionOrientation=ORIENTATION,termWipOnly=true;
let termSessions=['a','b','c','other'].map(name=>({name,logical_name:name,session_id:'uuid-'+name,cwd:'/workspace',kind:'terminal'}));
const originalSessions=JSON.stringify(termSessions),mutations=[];
const _TERM_WIP_ONLY_KEY='labTermWipOnly';
const _TERM_GROUPS_KEY='groups',_TERM_GROUP_COLORS=['#58a6ff'];
let _termDragState=null,_termDragLogical=null,_termReorderPending=false,_termGroupMenuOutside=null;
const _termActiveWorkspaceId=()=>workspace,_termVaultId=()=>vault,_termSessionsKey=(w,v)=>v+'::'+w;
const _termSessionMeta=name=>termSessions.find(s=>s.name===name),_termSessionDisplay=s=>s.name,_termRecentScopeKey=()=>workspace;
const termSessEsc=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const _termRenderActiveSessionHeader=()=>{},_termHideSessionTooltip=()=>{},_termShowSessionTooltip=()=>{},_termScheduleSessionTooltipHide=()=>{},_termClearLinkDropTarget=()=>{};
const termDeadSessions=new Set(),_termSessionVisual=()=>({kind:'terminal',badge:'Terminal',icon:'▣'}),_termSessionRecentMeta=()=>null,_termSessionIsWorking=()=>false;
const _termSessionContext=()=>({label:'Requests'}),_termSessionSummary=()=>'',_termSessionTooltipPayload=()=> '{}';
const _sidebarFileConfigScope='fixture',_sidebarFileConfig={folderScopes:[]},_loadSidebarFileConfig=()=>({folderScopes:[]}),_termScopeColor=s=>s.color||'#8b949e';
window.marked={};window.DOMPurify={};window.LabMarkdownEditor={create:(node,options)=>({value:options.body,destroy(){},focus(){}})};
const _termActivateTab=async name=>{termCurrentSession=name;termRenderSessionList()};
const termToggleCollapse=()=>document.body.classList.toggle('term-collapsed'),_termRememberVisibility=()=>{},_termVisibilityKey=()=>workspace,termStartPeriodicRefresh=()=>{};
const fixture={enabled:true,revision:'fixture',focused:['one','two','empty'],terminal_links:Object.fromEntries(termSessions.map(s=>[s.session_id,{objective_id:s.name==='other'?'two':'one',task_id:s.name}])),objectives:['one','two','empty'].map((id,i)=>({id,name:id,color:['#58a6ff','#bc8cff','#ffa657'][i],path:'/workspace/'+id,purpose:'',tasks:(id==='one'?['a','b','c']:id==='two'?['other']:[]).map(name=>({id:name,title:name,children:[],status:'in_progress',done:false})),resources:[],worktrees:[],shared_assets:[],unassigned_assets:[],archived_assets:[]}))};
window.fetch=async(url,options={})=>{if(options.method==='POST'){mutations.push(JSON.parse(options.body));return{ok:true,json:async()=>({})};}return{ok:true,json:async()=>structuredClone(fixture)}};
window.errors=[];window.addEventListener('error',e=>errors.push(e.error?.stack||e.message));window.addEventListener('unhandledrejection',e=>errors.push(String(e.reason)));
const created=[];
LabObjectives.connect({context:()=>({workspace_id:workspace,vault,path:'/workspace'}),refreshTabs:()=>document.querySelector('.repo-tabs').innerHTML=LabObjectives.tabsHtml('/workspace'),refreshTerminals:()=>termRenderSessionList(),prepareCenter:()=>{},scopeRoot:()=>'/workspace',
 sessions:()=>termSessions,parentTerminal:t=>termSessions.find(p=>p.logical_name===_termSubtabParents(_termReadGroupState(),termSessions)[t.logical_name]),
 activateLinkedTerminal:ids=>_termActivateObjectiveTerminal(ids),
 createWorkflowTerminal:async(launch)=>{created.push({launch,workflow:true});const s={name:'workflow-main',logical_name:'workflow-main',session_id:'uuid-workflow-main',cwd:launch.context.path,kind:'terminal'};termSessions.push(s);fixture.terminal_links[s.session_id]={main:'workflow'};fixture.revision+='!';await LabObjectives.load(undefined,true);return s;},
 createTaskTerminal:async(launch,task)=>{created.push({launch,task});const name='new-'+(task?.id||'global'),session={name,logical_name:name,session_id:'uuid-'+name,cwd:launch.path,kind:'terminal'};
 termSessions.push(session);fixture.terminal_links[session.session_id]={objective_id:launch.id,...(task?{task_id:task.id}:{})};fixture.revision+='!';await LabObjectives.load(undefined,true);await _termActivateTab(name);return session;}});
(async()=>{await LabObjectives.load();LabObjectives.openCurrent();termRenderSessionList();document.body.dataset.ready='true'})();
'''.replace('ORIENTATION', repr(orientation))
    css = LAB_SHELL_CSS.read_text() + (LAB_SHELL_CSS.parent / 'workspace-objectives.css').read_text()
    page = '<!doctype html><meta charset="utf-8"><style>'+css+' .term-panel{width:680px}.term-tabs-open{--term-sessions-width:230px}#sidebar{position:fixed;left:0;top:40px;width:230px;height:calc(100vh - 40px);overflow:auto}#content{margin-left:240px;width:calc(100vw - 920px)}</style><body class="term-open"><button id="outside">Outside</button><button id="termShowAllBtn" onclick="termToggleAllTerminals()">Show all terminals</button><div class="repo-tabs"></div><aside id="sidebar"><section data-objectives-sidebar></section></aside><main id="content"></main><section class="term-panel term-sessions-full '+('term-sessions-horizontal' if orientation=='horizontal' else '')+'"><div class="term-stage"><div class="term-session-switcher term-tabs-open"><div class="term-sessions" id="termSessionList"></div></div></div></section><div id="termGroupMenu" class="term-group-menu" hidden></div><script>'+OBJECTIVES.read_text()+'</script><script>'+GROUPS+MOVES+RENDER+ASSOCIATION+PILL+ALL_TOGGLE+OBJECTIVE_ACTIVATE+setup+'</script>'
    (tmp_path / 'fixture.html').write_text(page)
    class Handler(SimpleHTTPRequestHandler):
        def log_message(self, *args): pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Handler, directory=str(tmp_path)))
    Thread(target=server.serve_forever, daemon=True).start()
    profile = tmp_path / 'chrome'
    process = subprocess.Popen([chrome,'--headless=new','--no-first-run','--remote-debugging-port=0','--user-data-dir='+str(profile),'about:blank'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    driver = r'''
const fs=require('node:fs');
(async()=>{
 const assert=(ok,message)=>{if(!ok)throw Error(message)},sleep=ms=>new Promise(r=>setTimeout(r,ms));
 const [port]=fs.readFileSync(process.argv[1]+'/DevToolsActivePort','utf8').split('\n');
 const target=await fetch(`http://127.0.0.1:${port}/json/new?about:blank`,{method:'PUT'}).then(r=>r.json());
 const ws=new WebSocket(target.webSocketDebuggerUrl),pending=new Map();let sequence=0,dragData;
 ws.onmessage=e=>{const m=JSON.parse(e.data);if(m.method==='Input.dragIntercepted')dragData=m.params.data;if(m.id){const p=pending.get(m.id);pending.delete(m.id);m.error?p.reject(Error(m.error.message)):p.resolve(m.result)}};
 await new Promise(r=>ws.addEventListener('open',r,{once:true}));
 const send=(method,params={})=>new Promise((resolve,reject)=>{const id=++sequence;pending.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}))});
 async function evaluate(expression){const r=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(r.exceptionDetails)throw Error(r.exceptionDetails.exception?.description||'Browser assertion');return r.result.value;}
 const waitReady=async()=>{for(let i=0;i<300;i++){if(await evaluate('document.body?.dataset.ready==="true"'))return;await sleep(20)}throw Error('Fixture startup: '+await evaluate('errors.join("\\n")'))};
 const point=async selector=>evaluate(`(()=>{const n=document.querySelector(${JSON.stringify(selector)});if(!n?.getClientRects().length)throw Error('Invisible '+${JSON.stringify(selector)}+' '+JSON.stringify({wip:termWipOnly,node:n?.outerHTML,ancestors:n?[...(()=>{const a=[];for(let p=n.parentElement;p;p=p.parentElement)a.push([p.className,p.hidden,getComputedStyle(p).display]);return a})()]:[]}));n.scrollIntoView({block:'nearest'});const r=n.getBoundingClientRect();return{x:r.x+r.width/2,y:r.y+r.height/2}})()`);
 const move=p=>send('Input.dispatchMouseEvent',{type:'mouseMoved',...p});
 async function click(selector){const p=await point(selector);await move(p);await send('Input.dispatchMouseEvent',{type:'mousePressed',...p,button:'left',clickCount:1});await send('Input.dispatchMouseEvent',{type:'mouseReleased',...p,button:'left',clickCount:1});}
 async function drag(source,destination){dragData=null;const a=await point(source);await send('Input.setInterceptDrags',{enabled:true});await move(a);await send('Input.dispatchMouseEvent',{type:'mousePressed',...a,button:'left',buttons:1,clickCount:1});await send('Input.dispatchMouseEvent',{type:'mouseMoved',x:a.x+25,y:a.y+3,button:'left',buttons:1});for(let i=0;i<100&&!dragData;i++)await sleep(10);assert(dragData,'trusted drag starts');const b=await point(destination);await send('Input.dispatchDragEvent',{type:'dragEnter',...b,data:dragData});await send('Input.dispatchDragEvent',{type:'dragOver',...b,data:dragData});assert(await evaluate('mutations.length===0'),'hover sends no mutation');await send('Input.dispatchDragEvent',{type:'drop',...b,data:dragData});await send('Input.dispatchMouseEvent',{type:'mouseReleased',...b,button:'left',clickCount:1});await send('Input.setInterceptDrags',{enabled:false});}
 const tab=name=>'.sess[data-name="'+name+'"]';
 await send('Emulation.setDeviceMetricsOverride',{width:1500,height:1000,deviceScaleFactor:1,mobile:false});await send('Page.navigate',{url:process.argv[2]});await waitReady();
 assert(await evaluate(`document.querySelectorAll('.objective-terminal-heading').length===3&&document.querySelectorAll('.objective-terminal-rows:not([hidden])').length===1&&!document.querySelector('.sess[data-name=other]').getClientRects().length`),'initial Objective accordion');
 const saved=await evaluate('localStorage.getItem(_TERM_GROUPS_KEY)');
 await drag(tab('b'),tab('a'));
 assert(await evaluate(`!document.getElementById('termGroupMenu').hidden&&mutations.length===0&&localStorage.getItem(_TERM_GROUPS_KEY)===${JSON.stringify(saved)}`),'drop asks before changing layout');
 await click('[data-action=cancel]');assert(await evaluate('_termReadGroupState().tabParents.b===undefined&&mutations.length===0'),'cancel preserves layout');
 await drag(tab('b'),tab('a'));await click('[data-action=child]');await sleep(60);
 assert(await evaluate(`_termReadGroupState().tabParents.b==='a'&&document.querySelector('[data-term-parent=a] .sess[data-name=b]')&&mutations.length===1&&termCurrentSession==='b'`),'Make child commits hierarchy once and selects the new child');
 fs.writeFileSync(process.argv[1]+'/../subtabs.png',Buffer.from((await send('Page.captureScreenshot',{format:'png'})).data,'base64'));
 await click(tab('a'));await evaluate('LabObjectives.renderTasks()');
 await move(await point('#outside'));await evaluate('document.activeElement?.blur()');
 assert(await evaluate(`!document.querySelector('[data-term-parent=a] > .term-subtab-children').hidden&&document.querySelector('.sess[data-name=b]').getClientRects().length`),'WIP child stays visible without parent hover');
 await evaluate(`(async()=>{termWipOnly=false;fixture.objectives[0].tasks.find(t=>t.id==='b').status='todo';fixture.revision+='non-wip-hover';await LabObjectives.load(undefined,true);LabObjectives.renderTasks()})()`);
 await move(await point('#outside'));await evaluate('document.activeElement?.blur()');
 assert(await evaluate(`document.querySelector('[data-term-parent=a] > .term-subtab-children').hidden`),'child folds after leaving parent '+await evaluate(`JSON.stringify({current:termCurrentSession,focus:document.activeElement?.tagName,node:document.querySelector('[data-term-parent=a]')?.outerHTML})`));
 await move(await point(tab('a')));
 assert(await evaluate(`!document.querySelector('[data-term-parent=a] > .term-subtab-children').hidden&&document.querySelector('.sess[data-name=a]').getAttribute('aria-expanded')==='true'`),'hover unfolds child');
 const nodeIdentity=await evaluate(`window.oldChild=document.querySelector('.sess[data-name=b]');termRenderSessionList();oldChild===document.querySelector('.sess[data-name=b]')`);assert(nodeIdentity,'unchanged poll preserves hovered rows');
 await click(tab('b'));await move(await point('#outside'));assert(await evaluate(`!document.querySelector('.sess[data-name=b]').getClientRects().length&&termCurrentSession==='b'`),'selected non-WIP child folds without changing the active terminal');
 await evaluate(`(async()=>{termWipOnly=true;fixture.objectives[0].tasks.find(t=>t.id==='b').status='in_progress';fixture.revision+='wip-again';await LabObjectives.load(undefined,true)})()`);
 await evaluate(`(async()=>{fixture.enabled=false;await LabObjectives.load(undefined,true);termRenderSessionList()})()`);
 assert(await evaluate(`document.querySelector('[data-term-parent=a] .sess[data-name=b]')&&document.querySelector('.sess[data-name=other]').getClientRects().length>0`),'ordinary terminal rails preserve the same hierarchy');
 await evaluate(`(async()=>{fixture.enabled=true;await LabObjectives.load(undefined,true);termRenderSessionList()})()`);
 await click('.objective-terminal-heading[data-select-objective=two]');
 assert(await evaluate(`!document.querySelector('.sess[data-name=b]').getClientRects().length&&document.querySelector('.sess[data-name=other]').getClientRects().length>0&&document.querySelectorAll('.objective-terminal-rows:not([hidden])').length===1`),'terminal Objective header switches folded group');
 await move(await point('[data-current-objective]'));await click('.objective-switch-menu [data-select-objective=one]');
 assert(await evaluate(`document.querySelector('.sess[data-name=a]').getClientRects().length>0&&!document.querySelector('.sess[data-name=other]').getClientRects().length`),'dropdown switches same expanded group');
 await click('.objective-terminal-heading[data-select-objective=empty]');assert(await evaluate(`![...document.querySelectorAll('.sess[data-name]')].some(n=>n.getClientRects().length)&&document.querySelector('.term-task-placeholder').getClientRects().length>0&&document.querySelector('.term-new-tab').getClientRects().length>0`),'empty Objective offers its global terminal and folds other sessions');
 await click('.objective-terminal-heading[data-select-objective=one]');
 await click('[data-objective-terminals-all=one]');
 await evaluate('document.body.dataset.ready="false"');await send('Page.reload');await waitReady();assert(await evaluate(`_termReadGroupState().tabParents.b==='a'&&document.querySelector('[data-term-parent=a] .sess[data-name=b]')&&document.querySelector('[data-objective-terminals-all=one]').getAttribute('aria-pressed')==='true'`),'reload restores subtab relationship and Objective filter preference');
 await evaluate(`document.querySelector('.term-session-switcher').classList.remove('term-tabs-open');document.querySelector('[data-objective-terminals-all=one]').focus()`);
 await send('Input.dispatchKeyEvent',{type:'keyDown',key:' ',code:'Space',windowsVirtualKeyCode:32});await send('Input.dispatchKeyEvent',{type:'keyUp',key:' ',code:'Space',windowsVirtualKeyCode:32});
 assert(await evaluate(`document.querySelector('[data-objective-terminals-all=one]').getAttribute('aria-pressed')==='false'&&document.activeElement===document.querySelector('[data-objective-terminals-all=one]')&&(termSessionOrientation==='horizontal'||document.activeElement.getBoundingClientRect().right<=document.querySelector('.term-session-switcher').getBoundingClientRect().right)`),'Objective filter is reachable by keyboard, keeps focus and fits inside the compact vertical rail');
 await evaluate(`document.querySelector('.term-session-switcher').classList.add('term-tabs-open')`);
 await move(await point(tab('a')));await drag(tab('b'),tab('a'));await click('[data-action=below]');await sleep(60);
 assert(await evaluate(`!_termReadGroupState().tabParents.b&&_termReadGroupState().tabAfter.b==='a'&&!document.querySelector('[data-term-parent=a]')&&JSON.stringify(termSessions.map(s=>s.name))===JSON.stringify(['a','b','c','other'])`),'Move below makes child a sibling');
 assert(await evaluate(`JSON.stringify([...termSessions].sort((a,b)=>a.name.localeCompare(b.name)))===JSON.stringify(JSON.parse(originalSessions).sort((a,b)=>a.name.localeCompare(b.name)))&&errors.length===0`),'all terminal identities survive without browser errors');
 await evaluate(`(async()=>{
 termWipOnly=false;const o=fixture.objectives[0],makeTask=(id,children=[])=>({id,title:id,children,done:false,status:'todo',document_id:'details',tab_id:id,assets:[]});
 o.tasks=[makeTask('Parent task',[makeTask('Subtask')]),makeTask('Needs terminal')];
 o.resources=[{id:'details',kind:'document',title:'Details',path:'details.md',task_document:true,content:{body:'',revision:'details',tabs:o.tasks.flatMap(t=>[t,...t.children]).map(t=>({id:t.id,title:t.title,body:'Task details',parent:{id:'details'}}))}}];
 Object.assign(fixture.terminal_links,{'uuid-a':{objective_id:'one',task_id:'Parent task'},'uuid-b':{objective_id:'one',task_id:'Subtask'},'uuid-c':{objective_id:'one',view:'tasks'}});
 const group=_termReadGroupState();group.tabRoots=[];group.tabParents={c:'b'};group.tabAfter={};_termWriteGroupState(group);fixture.revision+='tasks';await LabObjectives.load(undefined,true);LabObjectives.renderTasks();
 })()`);
 assert(await evaluate(`document.querySelector('[data-term-parent=a] [data-term-parent=b] .sess[data-name=c]')&&document.querySelector('.sess[data-name=a] .sess-label').textContent==='Parent task'&&document.querySelector('.sess[data-name=a] .sess-task-status').dataset.taskStatus==='todo'&&getComputedStyle(document.querySelector('.sess[data-name=a] .sess-task-status')).width==='5px'&&!document.querySelector('.sess[data-name=a] .sess-icon')&&document.querySelector('.sess[data-name=c] .sess-task-status').dataset.taskStatus==='todo'&&!document.querySelector('.sess[data-name=c] .objective-task-default-icon')`),'task tree uses small status dots for primary and inherited child terminals');
 await move(await point(tab('a')));await move(await point(tab('b')));await click(tab('c'));
 assert(await evaluate(`LabObjectives.terminalLaunchContext().task.id==='Subtask'&&document.querySelector('.objective-task-mode-head').textContent.includes('Subtask')&&termCurrentSession==='c'&&!fixture.terminal_links['uuid-c'].task_id&&document.querySelector('.sess[data-name=c]').getAttribute('aria-label').includes('Parent task context: Subtask')`),'unassigned child selects inherited task and retains independent association');
 await move(await point('#outside'));await evaluate('document.activeElement?.blur()');await sleep(80);
 assert(await evaluate(`document.querySelector('[data-term-parent=a] > .term-subtab-children').hidden&&document.querySelector('[data-term-parent=b] > .term-subtab-children').hidden&&!document.querySelector('.sess[data-name=c]').getClientRects().length&&termCurrentSession==='c'`),'selected unassigned child and non-WIP ancestor fold after leaving the rail');
 fs.writeFileSync(process.argv[1]+'/../tasks.png',Buffer.from((await send('Page.captureScreenshot',{format:'png'})).data,'base64'));
 await click('[data-open-task-terminal="Needs terminal"]');await sleep(100);
 assert(await evaluate(`created.length===1&&created[0].task.id==='Needs terminal'&&fixture.terminal_links['uuid-new-Needs terminal'].task_id==='Needs terminal'&&termCurrentSession==='new-Needs terminal'&&!document.querySelector('[data-open-task-terminal="Needs terminal"]')`),'recommended task row starts one primary terminal');
 await evaluate(`LabObjectives.openTaskTerminal('Needs terminal','one')`);assert(await evaluate('created.length===1'),'task opening reuses its primary');
 await click('[data-terminal-objective=one][data-open-task-terminal=""]');await sleep(100);
 await evaluate(`LabObjectives.openTaskTerminal(null,'one')`);assert(await evaluate(`created.length===2&&created[1].task===null&&termCurrentSession==='new-global'&&errors.length===0`),'global row starts once and reuses project terminal');
 await evaluate(`(async()=>{
 const o=fixture.objectives[0],t=o.tasks[0];t.status='done';t.done=true;t.children.forEach(c=>{c.status='done';c.done=true;});o.tasks[1].status='in_progress';
 for(const [id,status] of [['Not started','todo'],['Completed without terminal','done']])o.tasks.push({id,title:id,children:[],done:status==='done',status,document_id:'details',tab_id:id,assets:[]});
 o.resources[0].content.tabs=o.tasks.flatMap(t=>[t,...t.children]).map(t=>({id:t.id,title:t.title,body:'Task details',parent:{id:'details'}}));
 fixture.revision+='statuses';termWipOnly=true;await LabObjectives.load(undefined,true);LabObjectives.renderTasks();
 })()`);
 assert(await evaluate(`document.querySelector('.sess[data-name="new-Needs terminal"]')&&!document.querySelector('.sess[data-name=a],.sess[data-name=b],.sess[data-name=c]')`),'default tabs only show WIP tasks');
 await click('.objective-sidebar-task [data-open-task="Parent task"]');await sleep(80);
 assert(await evaluate(`termCurrentSession==='a'&&document.querySelector('.sess[data-name=a]').classList.contains('active')&&created.length===2&&document.querySelector('.objective-sidebar-task.active').dataset.taskId==='Parent task'`),'completed task click reveals and selects existing primary without another session');
 await click('.objective-sidebar-task [data-open-task="Subtask"]');await sleep(80);
 assert(await evaluate(`termCurrentSession==='b'&&document.querySelector('.sess[data-name=b]')&&document.querySelector('.sess[data-name=c]')&&!document.querySelector('.sess[data-name=a]')&&created.length===2`),'completed subtask and inherited children remain visible without unrelated completed tasks');
 await evaluate(`document.body.classList.remove('term-open');document.body.classList.add('term-collapsed');document.querySelector('.objective-sidebar-task [data-open-task="Not started"]').click();document.querySelector('.objective-sidebar-task [data-open-task="Not started"]').click()`);await sleep(120);
 assert(await evaluate(`document.body.classList.contains('term-open')&&!document.body.classList.contains('term-collapsed')&&created.length===3&&termCurrentSession==='new-Not started'&&fixture.objectives[0].tasks.find(t=>t.id==='Not started').status==='todo'&&document.querySelector('.sess[data-name="new-Not started"]').classList.contains('active')`),'Todo task click automatically creates and selects one primary, preserving status');
 await click('.objective-sidebar-task [data-open-task="Completed without terminal"]');await sleep(120);
 assert(await evaluate(`created.length===4&&termCurrentSession==='new-Completed without terminal'&&fixture.objectives[0].tasks.find(t=>t.id==='Completed without terminal').done&&!document.querySelector('.sess[data-name="new-Not started"]')&&document.querySelector('.sess[data-name="new-Completed without terminal"]').classList.contains('active')`),'completed task without tmux session automatically creates and selects its primary');
 await click('.objective-sidebar-task [data-open-task="Not started"]');await sleep(80);
 assert(await evaluate(`created.length===4&&termCurrentSession==='new-Not started'`),'subsequent task click reuses automatically created terminal');
 await evaluate(`window.focusedTaskBeforeAll=LabObjectives.terminalLaunchContext().task.id;window.focusedCenterBeforeAll=document.querySelector('#content').innerHTML`);
 await click('[data-objective-terminals-all=one]');
 assert(await evaluate(`LabObjectives.terminalLaunchContext().task.id===focusedTaskBeforeAll&&termCurrentSession==='new-Not started'&&document.querySelector('#content').innerHTML===focusedCenterBeforeAll&&document.querySelector('.sess[data-name=a]')&&created.length===4`),'Objective Show all keeps the selected task and its terminal active');
 await click('[data-objective-terminals-all=one]');
 assert(await evaluate(`document.querySelector('.sess[data-name="new-Not started"]')&&!document.querySelector('.sess[data-name=a]')&&LabObjectives.terminalLaunchContext().task.id===focusedTaskBeforeAll`),'restoring WIP also keeps the selected Todo task terminal visible');
 await evaluate(`const count=created.length;LabObjectives.openForTerminal(termSessions.find(s=>s.name==='new-Not started'));window.creationsBeforePassive=count;LabObjectives.renderTasks()`);
 assert(await evaluate(`created.length===creationsBeforePassive&&!document.querySelector('.sess[data-name="new-Not started"],.sess[data-name="new-Completed without terminal"]')&&document.querySelector('.sess[data-name="new-Needs terminal"]')&&errors.length===0`),'leaving task focus restores WIP tabs and passive terminal navigation never creates another session');

 await evaluate(`window.taskBeforeAll=LabObjectives.terminalLaunchContext().task;window.sessionBeforeAll=termCurrentSession;window.centerBeforeAll=document.querySelector('#content').innerHTML`);
 await click('[data-objective-terminals-all=one]');
 assert(await evaluate(`termWipOnly&&document.querySelector('[data-objective-terminals-all=one]').getAttribute('aria-pressed')==='true'&&document.querySelector('.sess[data-name=a]')&&document.querySelector('.sess[data-name=b]')&&document.querySelector('.sess[data-name=c]')&&document.querySelector('.sess[data-name="new-Not started"]')&&document.querySelector('.sess[data-name="new-Completed without terminal"]')&&document.querySelectorAll('.objective-terminal-rows:not([hidden])').length===1&&!document.querySelector('.sess[data-name=other]').getClientRects().length&&document.querySelectorAll('[data-terminal-main]').length===2&&created.length===4&&termCurrentSession===sessionBeforeAll&&LabObjectives.terminalLaunchContext().task===taskBeforeAll&&document.querySelector('#content').innerHTML===centerBeforeAll`),'Objective Show all reveals every status and child without opening other groups, creating sessions or changing task focus');
 assert(await evaluate(`JSON.parse(localStorage.getItem('lab.objectives.view.v1:fixture::demo')).terminalAll.one===true`),'Objective filter preference persists per workspace');
 await click('.objective-terminal-heading[data-select-objective=two]');
 assert(await evaluate(`document.querySelector('[data-terminal-main=workflow]')&&document.querySelector('[data-terminal-main=objective][data-terminal-objective=two]')&&!document.querySelector('[data-terminal-main=objective][data-terminal-objective=one]')&&!document.querySelector('[data-objective-terminals-all=one]')&&document.querySelector('[data-objective-terminals-all=two]').getAttribute('aria-pressed')==='false'&&!document.querySelector('.sess[data-name=a]')&&document.querySelectorAll('.objective-terminal-rows:not([hidden])').length===1`),'switching Objective preserves the workspace main and shows only the current Objective main and its own filter');
 await click('.objective-terminal-heading[data-select-objective=one]');
 assert(await evaluate(`document.querySelector('[data-objective-terminals-all=one]').getAttribute('aria-pressed')==='true'&&document.querySelector('.sess[data-name=a]')`),'returning to an Objective restores its Show all preference');
 await click('[data-objective-terminals-all=one]');
 assert(await evaluate(`termWipOnly&&!document.querySelector('.sess[data-name=a],.sess[data-name="new-Not started"]')&&document.querySelector('.sess[data-name="new-Needs terminal"]')&&document.querySelector('[data-objective-terminals-all=one]').getAttribute('aria-pressed')==='false'&&created.length===4`),'Objective toggle restores WIP plus selected task');

 await click('#termShowAllBtn');
 assert(await evaluate(`!termWipOnly&&localStorage.getItem(_TERM_WIP_ONLY_KEY)==='false'&&document.querySelectorAll('.objective-terminal-rows:not([hidden])').length===3&&document.querySelector('.sess[data-name=a]').getClientRects().length>0&&document.querySelector('.sess[data-name=other]').getClientRects().length>0&&document.getElementById('termShowAllBtn').getAttribute('aria-pressed')==='true'&&document.querySelectorAll('[data-terminal-main]').length===2&&document.querySelector('[data-objective-terminals-all=one]').disabled`),'global Show all reveals every Objective and completed task terminal while inactive Objective mains remain hidden');
 await click('#termShowAllBtn');
 assert(await evaluate(`termWipOnly&&document.querySelectorAll('.objective-terminal-rows:not([hidden])').length===1&&!document.querySelector('.sess[data-name=a]')&&document.querySelectorAll('[data-terminal-main]').length===2`),'toggle restores one expanded Objective and only the workspace and active Objective mains');
 await evaluate(`const main=document.querySelector('[data-terminal-main=workflow]');main.click();main.click()`);await sleep(100);
 assert(await evaluate(`created.length===5&&created[4].workflow&&termCurrentSession==='workflow-main'&&document.getElementById('termSessionList').firstElementChild.dataset.name==='workflow-main'&&document.querySelector('.sess[data-name=workflow-main]').getAttribute('draggable')==='false'&&!document.querySelector('.sess[data-name=workflow-main]').hasAttribute('data-order-token')&&document.querySelector('.objective-terminal-heading[data-select-objective=one]').parentElement.nextElementSibling.dataset.name==='new-global'`),'one fixed workflow main at top and Objective main immediately after its divider');
 await click('.sess[data-name=workflow-main]');assert(await evaluate('created.length===5'),'workflow main reuses the saved session');
 for(const [status,label] of [['paused','Paused'],['wont_do','Won’t do']]){
  await evaluate(`(async()=>{const t=fixture.objectives[0].tasks.find(t=>t.id==='Not started');t.status=${JSON.stringify(status)};fixture.revision+='status';await LabObjectives.load(undefined,true);LabObjectives.renderTasks()})()`);
  assert(await evaluate(`!document.querySelector('.sess[data-name="new-Not started"]')`),'paused and declined terminals hidden by default');
  await click('.objective-sidebar-task [data-open-task="Not started"]');await sleep(80);
  assert(await evaluate(`termCurrentSession==='new-Not started'&&created.length===5&&document.querySelector('.sess[data-name="new-Not started"] .sess-task-status').dataset.taskStatus===${JSON.stringify(status)}&&document.querySelector('.sess[data-name="new-Not started"]').getAttribute('aria-label').includes(${JSON.stringify(label)})`),'selected paused or declined task reveals its primary and accessible status dot');
 }
 await evaluate(`(async()=>{
 const o=fixture.objectives[0];o.worktrees=[{id:'ui',label:'sdui/jcortes/tel',path:'/trees/ui',repo:'/workspace',kind:'worktree',color:'#ff7b72'},{id:'checkpoint',label:'checkpoint/jco',path:'/trees/checkpoint',repo:'/workspace',kind:'worktree',color:'#58a6ff'}];
 o.tasks.find(t=>t.id==='Not started').assets=[{id:'ui-asset',folder:{root:'/trees/ui',path:'.'}},{id:'checkpoint-asset',folder:{root:'/trees/checkpoint',path:'.'}}];
 o.tasks.push({id:'Recommended',title:'Recommended',children:[],assets:[{id:'recommend-asset',folder:{root:'/trees/checkpoint',path:'.'}}],status:'todo',done:false});
 const name='worktree-only';termSessions.push({name,logical_name:name,session_id:'uuid-'+name,kind:'terminal',cwd:'/trees/ui',linked_scope:{root:'/trees/ui',project_root:'/workspace',worktree:'/trees/ui',label:'sdui/jcortes · ui',color:'#ff7b72'}});fixture.terminal_links['uuid-'+name]={objective_id:'one',folder:{root:'/trees/ui',path:'.'}};
 fixture.revision+='colors';await LabObjectives.load(undefined,true);
 })()`);
 assert(await evaluate(`(()=>{const row=document.querySelector('.sess[data-name="new-Not started"]');return row.querySelector('.sess-label').textContent==='Not started'&&!row.querySelector('.objective-task-worktree-name,.term-folder-association')&&row.querySelector('.sess-task-status').dataset.taskStatus==='wont_do'&&fixture.objectives[0].tasks.find(t=>t.id==='Not started').title==='Not started'&&row.getAttribute('aria-label').includes('Won’t do')})()`),'multiple worktrees keep the canonical task terminal name and small status dot');
 await click('[data-objective-terminals-all=one]');
 assert(await evaluate(`(()=>{const row=document.querySelector('[data-open-task-terminal=Recommended]');return row.querySelector('.objective-task-worktree-name').textContent==='checkpoint/jco'&&getComputedStyle(row.querySelector('.objective-task-worktree-name')).color==='rgb(88, 166, 255)'&&!row.querySelector('.sess-task-status')&&row.getAttribute('aria-label').includes('Not started')&&created.length===5})()`),'recommended terminals retain their colored bullet without another status dot');
 assert(await evaluate(`(()=>{const row=document.querySelector('.sess[data-name=worktree-only]'),label=row.querySelector('.term-folder-association');return !row.querySelector('.sess-icon')&&label.textContent==='sdui/jcortes/ui'&&getComputedStyle(label).color==='rgb(255, 123, 114)'&&getComputedStyle(label,'::before').width==='6px'&&getComputedStyle(row).backgroundColor==='rgba(0, 0, 0, 0)'})()`),'worktree terminal is a plain row with matching colored dot and text');
 await evaluate(`document.querySelector('.term-session-switcher').classList.remove('term-tabs-open')`);
 assert(await evaluate(`(()=>{const row=document.querySelector('.sess[data-name="new-Not started"]'),label=row.querySelector('.sess-label'),dot=row.querySelector('.sess-task-status');return dot.getClientRects().length&&getComputedStyle(dot).width==='5px'&&!row.querySelector('.objective-task-worktree-name')&&(termSessionOrientation==='horizontal'||getComputedStyle(label).display==='none')})()`),'compact rail uses one small status dot for a task with multiple worktrees');
 await evaluate(`document.querySelector('.term-session-switcher').classList.add('term-tabs-open')`);
 await evaluate(`(async()=>{fixture.objectives[0].tasks.find(t=>t.id==='Not started').assets.splice(1);fixture.revision+='single-worktree';await LabObjectives.load(undefined,true)})()`);
 assert(await evaluate(`(()=>{const row=document.querySelector('.sess[data-name="new-Not started"]'),label=row.querySelector('.objective-task-worktree-name');return label?.textContent==='sdui/jcortes/tel'&&getComputedStyle(label).color==='rgb(255, 123, 114)'&&!row.querySelector('.sess-task-status')&&fixture.objectives[0].tasks.find(t=>t.id==='Not started').title==='Not started'})()`),'exactly one worktree replaces the task terminal label with its existing colored bullet');
 fs.writeFileSync(process.argv[1]+'/../terminal-dots.png',Buffer.from((await send('Page.captureScreenshot',{format:'png'})).data,'base64'));
 assert(await evaluate('errors.length===0'),'no browser errors with main roles, Show all, paused or declined tasks');
 await evaluate(`(async()=>{
 const o=fixture.objectives[0],parent=o.tasks.find(t=>t.id==='Parent task');parent.status='in_progress';parent.done=false;parent.children[0].status='in_progress';parent.children[0].done=false;
 o.tasks.push({id:'Second parent',title:'Second parent',status:'todo',done:false,assets:[],children:[{id:'Second WIP',title:'Second WIP',status:'in_progress',done:false,children:[],assets:[]},{id:'Second Todo',title:'Second Todo',status:'todo',done:false,children:[],assets:[]}]});
 const name='automation-'+('a'.repeat(32))+'-1';termSessions.push({name,logical_name:name,session_id:'uuid-'+name,kind:'terminal',cwd:'/workspace'});fixture.terminal_links['uuid-'+name]={objective_id:'one',view:'tasks'};const group=_termReadGroupState();group.tabParents[name]='a';_termWriteGroupState(group);window.automationName=name;
 fixture.revision+='persistent-wip';termWipOnly=true;await LabObjectives.load(undefined,true);LabObjectives.renderTasks();await _termActivateTab('workflow-main');
 const filter=document.querySelector('[data-objective-terminals-all=one]');if(filter.getAttribute('aria-pressed')==='true')filter.click();
 })()`);
 await move(await point('#outside'));await evaluate('document.activeElement?.blur()');
 assert(await evaluate(`['Subtask','Second WIP'].every(id=>document.querySelector('.objective-sidebar-task[data-task-id="'+id+'"]').getClientRects().length>0)&&!document.querySelector('.objective-sidebar-task[data-task-id="Second Todo"]')`),'WIP subtasks under multiple parents remain in Tasks without selection');
 assert(await evaluate(`document.querySelector('.sess[data-name=b]').getClientRects().length>0&&!document.querySelector('.sess[data-name=c]').getClientRects().length&&!document.querySelector('.sess[data-name="'+automationName+'"]').getClientRects().length&&document.querySelector('[data-open-task-terminal="Second WIP"]').getClientRects().length>0&&created.length===5`),'own WIP primaries and recommendations stay visible while inherited and automation siblings fold');
 await evaluate(`document.querySelector('.sess[data-name=a]').dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowLeft',bubbles:true}))`);
 assert(await evaluate(`!document.querySelector('[data-term-parent=a] > .term-subtab-children').hidden&&document.querySelector('[data-term-parent=b] > .term-subtab-children').hidden`),'keyboard collapse keeps own WIP children visible without exposing inherited children');
 await move(await point(tab('a')));
 assert(await evaluate(`document.querySelector('.sess[data-name=b]').getClientRects().length>0&&document.querySelector('.sess[data-name="'+automationName+'"]').getClientRects().length>0&&!document.querySelector('.sess[data-name=c]').getClientRects().length`),'parent hover reveals only its own automation children beside WIP rows');
 await evaluate(`termSessions.find(s=>s.name===automationName).label='Automation changed';termRenderSessionList()`);
 assert(await evaluate(`document.querySelector('.sess[data-name="'+automationName+'"]').getClientRects().length>0`),'changed polling restores the hovered parent');
 await move(await point(tab('b')));
 assert(await evaluate(`document.querySelector('.sess[data-name=c]').getClientRects().length>0`),'nested parent hover reveals inherited child');
 await move(await point('#outside'));
 assert(await evaluate(`document.querySelector('.sess[data-name=b]').getClientRects().length>0&&!document.querySelector('.sess[data-name=c]').getClientRects().length&&!document.querySelector('.sess[data-name="'+automationName+'"]').getClientRects().length`),'leaving mixed nested branches folds hover-only rows and retains WIP');
 await move(await point(tab('a')));await click(tab(await evaluate('automationName')));await move(await point('#outside'));
 assert(await evaluate(`termCurrentSession===automationName&&!document.querySelector('.sess[data-name="'+automationName+'"]').getClientRects().length&&document.querySelector('.sess[data-name=b]').getClientRects().length>0`),'selected automation also folds while its terminal remains active');
 await evaluate(`document.querySelector('.sess[data-name=a]').focus()`);await send('Input.dispatchKeyEvent',{type:'keyDown',key:'ArrowRight',code:'ArrowRight',windowsVirtualKeyCode:39});await send('Input.dispatchKeyEvent',{type:'keyUp',key:'ArrowRight',code:'ArrowRight',windowsVirtualKeyCode:39});
 assert(await evaluate(`document.querySelector('.sess[data-name="'+automationName+'"]').getClientRects().length>0`),'keyboard navigation can reveal hover-only children');
 await click('#outside');
 assert(await evaluate(`!document.querySelector('.sess[data-name="'+automationName+'"]').getClientRects().length&&document.querySelector('.sess[data-name=b]').getClientRects().length>0`),'leaving keyboard focus folds only hover-only children');
 await evaluate(`_termActivateTab('workflow-main')`);
 await evaluate(`(async()=>{
 const o=fixture.objectives[0];o.tasks.push({id:'Deep WIP',title:'Deep WIP',status:'in_progress',done:false,children:[],assets:[]});
 const name='deep-wip';termSessions.push({name,logical_name:name,session_id:'uuid-'+name,kind:'terminal',cwd:'/workspace'});fixture.terminal_links['uuid-'+name]={objective_id:'one',task_id:'Deep WIP'};
 const group=_termReadGroupState();group.tabParents[name]='c';_termWriteGroupState(group);fixture.revision+='deep-wip';await LabObjectives.load(undefined,true);
 })()`);
 assert(await evaluate(`document.querySelector('.sess[data-name=deep-wip]').getClientRects().length>0&&!document.querySelector('.sess[data-name=c]').getClientRects().length&&document.querySelector('.sess[data-name=b]').getClientRects().length>0`),'deep own-WIP terminal stays visible without exposing its unassigned ancestor row');
 await move(await point(tab('b')));
 assert(await evaluate(`document.querySelector('.sess[data-name=c]').getClientRects().length>0&&document.querySelector('.sess[data-name=deep-wip]').getClientRects().length>0`),'ancestor row is still available on its parent hover');
 await move(await point('#outside'));
 assert(await evaluate(`!document.querySelector('.sess[data-name=c]').getClientRects().length&&document.querySelector('.sess[data-name=deep-wip]').getClientRects().length>0`),'leaving hides the ancestor row while preserving deep WIP visibility');
 await evaluate(`(async()=>{fixture.objectives[0].tasks.pop();termSessions=termSessions.filter(s=>s.name!=='deep-wip');delete fixture.terminal_links['uuid-deep-wip'];fixture.revision+='remove-deep-fixture';await LabObjectives.load(undefined,true)})()`);
 await evaluate(`(async()=>{const o=fixture.objectives[0];o.tasks[0].children[0].status='done';o.tasks[0].children[0].done=true;o.tasks.at(-1).children[0].status='done';o.tasks.at(-1).children[0].done=true;fixture.revision+='wip-completed';await LabObjectives.load(undefined,true);LabObjectives.renderTasks()})()`);
 assert(await evaluate(`!document.querySelector('.objective-sidebar-task[data-task-id="Subtask"],.objective-sidebar-task[data-task-id="Second WIP"]')&&!document.querySelector('.sess[data-name=b],.sess[data-name=c],[data-open-task-terminal="Second WIP"]')&&created.length===5&&errors.length===0`),'completed children return to normal disclosure and filtering after refresh');
 ws.close();console.log('PASS');
})().catch(e=>{console.error(e.stack);process.exit(1)});
'''
    try:
        deadline = time.monotonic() + 10
        while not (profile / 'DevToolsActivePort').exists():
            assert process.poll() is None and time.monotonic() < deadline, 'Chrome did not start'
            time.sleep(.05)
        result = subprocess.run(['node','-e',driver,str(profile),f'http://127.0.0.1:{server.server_port}/fixture.html'], capture_output=True, text=True, timeout=60)
        assert result.returncode == 0, result.stdout + result.stderr
        assert 'PASS' in result.stdout
    finally:
        process.terminate(); process.wait(timeout=10)
        server.shutdown(); server.server_close()


def test_automation_children_of_mains_remain_available_on_hover_and_inherit_status():
    source = OBJECTIVES.read_text()
    helpers = source[source.index('  function terminalIdentity('):source.index('  function sidebarTarget(')]
    result = _run_node(r'''
const _TERM_GROUP_COLORS=['#58a6ff'],tasks=o=>o?.tasks||[],taskStatus=t=>t.status,taskDisplayName=t=>t.title,taskIcon=()=>'',customTaskIcon=()=>'',esc=String,termSessEsc=String,_termSessionDisplay=t=>t.name;
const o={id:'one',name:'One',tasks:[{id:'wip',title:'Working',status:'in_progress',children:[]},{id:'done',title:'Done',status:'done',children:[]}],worktrees:[],resources:[]};
const two={id:'two',name:'Two',tasks:[],worktrees:[],resources:[]};
const registry={enabled:true,focused:['one','two'],objectives:[o,two],terminal_links:{workflow:{main:'workflow'},main:{objective_id:'one',main:'objective'},other:{objective_id:'two',main:'objective'},
 'workflow-service':{view:'workflow'},nested:{view:'workflow'},'main-service':{objective_id:'one',view:'tasks'},'other-service':{objective_id:'two',view:'tasks'},
 wip:{objective_id:'one',task_id:'wip'},'wip-service':{objective_id:'one',view:'tasks'},done:{objective_id:'one',task_id:'done'},'done-service':{objective_id:'one',view:'tasks'}}};
const sessions=Object.keys(registry.terminal_links).map(name=>({name,logical_name:name,session_id:name})),termSessions=sessions;
let termCurrentSession='workflow-service',selected=null;
const context=()=>({path:'/fixture',workspace_id:'demo'}),data=()=>registry,active=()=>true,objective=()=>o,focusedTask=()=>selected,state=()=>({});
const explicit={'workflow-service':'workflow',nested:'workflow-service','main-service':'main','other-service':'other','wip-service':'wip','done-service':'done'};
const bridge={parentTerminal:t=>sessions.find(s=>s.logical_name===explicit[t.logical_name])};
''' + helpers + GROUPS + r'''
window.LabObjectives={terminalParents,terminalMain,terminalExpanded,sameTerminalObjective:(a,b)=>terminalObjective(a)?.id===terminalObjective(b)?.id};
const defaults=terminalSessions(sessions),group=_termNormalizeGroupState({order:sessions.map(s=>'s:'+s.name),tabParents:explicit});
const html=terminalHtml(defaults,_termSubtabRenderer(group,defaults,t=>`<span class="sess" role="tab" data-name="${t.name}">${t.name}</span>`),'',{arrange:rows=>_termArrangeSubtabRows(rows,group)});
selected=o.tasks[1];const withSelected=terminalSessions(sessions);
console.log(JSON.stringify({names:defaults.map(t=>t.name),selected:withSelected.map(t=>t.name),parents:terminalParents(sessions,{...explicit,workflow:'nested'}),html}));
''')
    assert set(result['names']) == {'workflow','main','wip','workflow-service','nested','main-service','wip-service'}
    assert {'done','done-service'} <= set(result['selected'])
    assert result['parents']['workflow-service'] == 'workflow' and 'workflow' not in result['parents']
    assert result['html'].index('data-name="workflow"') < result['html'].index('data-name="workflow-service"')
    assert 'data-term-parent="main"' in result['html'] and 'data-name="other-service"' not in result['html']


def test_main_rows_pin_workflow_and_active_objective_and_reuse_workflow_creation():
    source = OBJECTIVES.read_text()
    helpers = source[source.index('  function terminalIdentity('):source.index('  function sidebarTarget(')]
    result = _run_node(r'''
const tasks=o=>o?.tasks||[],taskStatus=t=>t.status,taskDisplayName=t=>t.title,taskIcon=()=>'',customTaskIcon=()=>'',esc=String;
const o={id:'one',name:'One',tasks:[{id:'done',title:'Done',status:'done',children:[]}],worktrees:[],resources:[]};
const two={id:'two',name:'Two',tasks:[],worktrees:[]};
const parked={id:'parked',name:'Parked',tasks:[],worktrees:[]};
const registry={enabled:true,focused:['one','two'],objectives:[o,two,parked],terminal_links:{
 duplicate:{objective_id:'one'},main:{objective_id:'one',main:'objective'},'two-main':{objective_id:'two',main:'objective'},done:{objective_id:'one',task_id:'done'},parked:{objective_id:'parked',view:'tasks'}}};
const sessions=['duplicate','done','main','two-main','parked'].map(name=>({name,session_id:name,logical_name:name}));
let current=o;
const context=()=>({path:'/workflow',vault:'fixture',workspace_id:'work'}),data=()=>registry,active=()=>true,objective=()=>current,focusedTask=()=>null;
const view={terminalAll:{}},state=()=>view;
const key=s=>s.vault+'::'+s.workspace_id;
const activated=[],created=[];let finish;
const bridge={workflowName:()=> 'Workflow',sessions:()=>sessions,activateLinkedTerminal:ids=>activated.push(ids),
 createWorkflowTerminal:launch=>{created.push(launch);return new Promise(r=>finish=r)}};
''' + helpers + r'''
const defaults=terminalSessions(sessions),all=terminalSessions(sessions,{wipOnly:false});
const pill=t=>`<tab data-name="${t.name}" data-main="${terminalMain(t)?.kind||''}"></tab>`;
const html=terminalHtml(defaults,pill,'<new>',{arrange:rows=>rows.reverse()}),allHtml=terminalHtml(all,pill,'<new>',{showAll:true});
current=two;const switched=terminalSessions(sessions);current=o;
view.terminalAll.one=true;const objectiveAll=terminalSessions(sessions);view.terminalAll.one=false;
const parents=terminalParents(all,{main:'done',done:'main'});
(async()=>{
 const a=openMainTerminal('workflow'),b=openMainTerminal('workflow');finish({name:'workflow',session_id:'workflow'});await Promise.all([a,b]);
 sessions.push({name:'workflow',session_id:'workflow',logical_name:'workflow'});registry.terminal_links.workflow={main:'workflow'};
 await openMainTerminal('workflow');
 console.log(JSON.stringify({defaults:defaults.map(s=>s.name),switched:switched.map(s=>s.name),objectiveAll:objectiveAll.map(s=>s.name),roles:sessions.map(s=>[s.name,terminalMain(s)?.kind||null]),html,allHtml,parents,created,activated}));
})().catch(e=>{console.error(e);process.exit(1)});
''')
    assert result['defaults'] == ['workflow-terminal:work:main', 'main']
    assert result['switched'] == ['workflow-terminal:work:main', 'two-main']
    assert result['objectiveAll'] == ['workflow-terminal:work:main', 'main', 'done', 'duplicate']
    assert dict(result['roles']) == {'duplicate':None,'done':None,'main':'objective','two-main':'objective','parked':None,'workflow':'workflow'}
    # A main stays a root, but can host automation children.
    assert result['parents'] == {'done': 'main'}
    assert result['html'].startswith('<tab data-name="workflow-terminal:work:main"')
    assert '</div><tab data-name="main" data-main="objective"></tab><div class="objective-terminal-rows">' in result['html']
    assert 'data-select-objective="two"' in result['html'] and 'data-name="objective-terminal:two:global"' not in result['html']
    assert result['html'].count('data-objective-terminals-all=') == 1
    assert 'Show all terminals in this Objective' in result['html']
    assert ' hidden' not in result['allHtml'] and 'data-name="done"' in result['allHtml']
    assert 'data-name="two-main"' not in result['allHtml']
    assert 'data-select-objective="parked"' in result['allHtml'] and 'data-name="parked"' in result['allHtml']
    assert len(result['created']) == 1
    assert result['activated'] == [['workflow'], ['workflow']]
