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
PILL = _js_between('  function _termSessionPillHtml(', '  function _termMarkVisibleCompletionSeen(')
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
    assert result['html'].count(' hidden') == 2
    assert ' hidden' not in result['activeHtml']


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
const _termSessionContext=()=>({label:'Requests'}),_termSessionSummary=()=>'',_termSessionTooltipPayload=()=> '{}',_termSessionAssociationHtml=()=>'';
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
    page = '<!doctype html><meta charset="utf-8"><style>'+css+' .term-panel{width:680px}.term-tabs-open{--term-sessions-width:230px}#sidebar{position:fixed;left:0;top:40px;width:230px;height:calc(100vh - 40px);overflow:auto}#content{margin-left:240px;width:calc(100vw - 920px)}</style><body class="term-open"><button id="outside">Outside</button><button id="termShowAllBtn" onclick="termToggleAllTerminals()">Show all terminals</button><div class="repo-tabs"></div><aside id="sidebar"><section data-objectives-sidebar></section></aside><main id="content"></main><section class="term-panel term-sessions-full '+('term-sessions-horizontal' if orientation=='horizontal' else '')+'"><div class="term-stage"><div class="term-session-switcher term-tabs-open"><div class="term-sessions" id="termSessionList"></div></div></div></section><div id="termGroupMenu" class="term-group-menu" hidden></div><script>'+OBJECTIVES.read_text()+'</script><script>'+GROUPS+MOVES+RENDER+PILL+ALL_TOGGLE+OBJECTIVE_ACTIVATE+setup+'</script>'
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
 assert(await evaluate(`document.querySelector('[data-term-parent=a] > .term-subtab-children').hidden`),'child folds after leaving parent '+await evaluate(`JSON.stringify({current:termCurrentSession,focus:document.activeElement?.tagName,node:document.querySelector('[data-term-parent=a]')?.outerHTML})`));
 await move(await point(tab('a')));
 assert(await evaluate(`!document.querySelector('[data-term-parent=a] > .term-subtab-children').hidden&&document.querySelector('.sess[data-name=a]').getAttribute('aria-expanded')==='true'`),'hover unfolds child');
 const nodeIdentity=await evaluate(`window.oldChild=document.querySelector('.sess[data-name=b]');termRenderSessionList();oldChild===document.querySelector('.sess[data-name=b]')`);assert(nodeIdentity,'unchanged poll preserves hovered rows');
 await click(tab('b'));await move(await point('#outside'));assert(await evaluate(`document.querySelector('.sess[data-name=b]').getClientRects().length>0&&termCurrentSession==='b'`),'selected child remains available');
 await evaluate(`(async()=>{fixture.enabled=false;await LabObjectives.load(undefined,true);termRenderSessionList()})()`);
 assert(await evaluate(`document.querySelector('[data-term-parent=a] .sess[data-name=b]')&&document.querySelector('.sess[data-name=other]').getClientRects().length>0`),'ordinary terminal rails preserve the same hierarchy');
 await evaluate(`(async()=>{fixture.enabled=true;await LabObjectives.load(undefined,true);termRenderSessionList()})()`);
 await click('.objective-terminal-heading[data-select-objective=two]');
 assert(await evaluate(`!document.querySelector('.sess[data-name=b]').getClientRects().length&&document.querySelector('.sess[data-name=other]').getClientRects().length>0&&document.querySelectorAll('.objective-terminal-rows:not([hidden])').length===1`),'terminal Objective header switches folded group');
 await move(await point('[data-current-objective]'));await click('.objective-switch-menu [data-select-objective=one]');
 assert(await evaluate(`document.querySelector('.sess[data-name=a]').getClientRects().length>0&&!document.querySelector('.sess[data-name=other]').getClientRects().length`),'dropdown switches same expanded group');
 await click('.objective-terminal-heading[data-select-objective=empty]');assert(await evaluate(`![...document.querySelectorAll('.sess[data-name]')].some(n=>n.getClientRects().length)&&document.querySelector('.term-task-placeholder').getClientRects().length>0&&document.querySelector('.term-new-tab').getClientRects().length>0`),'empty Objective offers its global terminal and folds other sessions');
 await click('.objective-terminal-heading[data-select-objective=one]');
 await evaluate('document.body.dataset.ready="false"');await send('Page.reload');await waitReady();assert(await evaluate(`_termReadGroupState().tabParents.b==='a'&&document.querySelector('[data-term-parent=a] .sess[data-name=b]')`),'reload restores subtab relationship');
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
 assert(await evaluate(`document.querySelector('[data-term-parent=a] [data-term-parent=b] .sess[data-name=c]')&&document.querySelector('.sess[data-name=a] .sess-label').textContent==='Parent task'&&document.querySelector('.sess[data-name=a] .sess-task-status').textContent==='⬜'&&!document.querySelector('.sess[data-name=a] .sess-icon')`),'task-shaped terminal tree and status match task organization');
 await move(await point(tab('a')));await move(await point(tab('b')));await click(tab('c'));
 assert(await evaluate(`LabObjectives.terminalLaunchContext().task.id==='Subtask'&&document.querySelector('.objective-task-mode-head').textContent.includes('Subtask')&&termCurrentSession==='c'&&!fixture.terminal_links['uuid-c'].task_id&&document.querySelector('.sess[data-name=c]').getAttribute('aria-label').includes('Parent task context: Subtask')`),'unassigned child selects inherited task and retains independent association');
 await move(await point('#outside'));await evaluate('document.activeElement?.blur()');await sleep(80);
 assert(await evaluate(`!document.querySelector('[data-term-parent=a] > .term-subtab-children').hidden&&!document.querySelector('[data-term-parent=b] > .term-subtab-children').hidden&&document.querySelector('.sess[data-name=c]').getClientRects().length>0`),'task ancestors keep the selected extra subterminal unfolded after leaving the rail');
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
 await evaluate(`const count=created.length;LabObjectives.openForTerminal(termSessions.find(s=>s.name==='new-Not started'));window.creationsBeforePassive=count;LabObjectives.renderTasks()`);
 assert(await evaluate(`created.length===creationsBeforePassive&&!document.querySelector('.sess[data-name="new-Not started"],.sess[data-name="new-Completed without terminal"]')&&document.querySelector('.sess[data-name="new-Needs terminal"]')&&errors.length===0`),'leaving task focus restores WIP tabs and passive terminal navigation never creates another session');

 await click('#termShowAllBtn');
 assert(await evaluate(`!termWipOnly&&localStorage.getItem(_TERM_WIP_ONLY_KEY)==='false'&&document.querySelectorAll('.objective-terminal-rows:not([hidden])').length===3&&document.querySelector('.sess[data-name=a]').getClientRects().length>0&&document.querySelector('.sess[data-name=other]').getClientRects().length>0&&document.getElementById('termShowAllBtn').getAttribute('aria-pressed')==='true'`),'Show all reveals every Objective and completed task terminal');
 await click('#termShowAllBtn');
 assert(await evaluate(`termWipOnly&&document.querySelectorAll('.objective-terminal-rows:not([hidden])').length===1&&!document.querySelector('.sess[data-name=a]')&&document.querySelectorAll('[data-terminal-main]').length===4`),'toggle restores one expanded Objective and keeps every main');
 await evaluate(`const main=document.querySelector('[data-terminal-main=workflow]');main.click();main.click()`);await sleep(100);
 assert(await evaluate(`created.length===5&&created[4].workflow&&termCurrentSession==='workflow-main'&&document.getElementById('termSessionList').firstElementChild.dataset.name==='workflow-main'&&document.querySelector('.sess[data-name=workflow-main]').getAttribute('draggable')==='false'&&!document.querySelector('.sess[data-name=workflow-main]').hasAttribute('data-order-token')&&document.querySelector('.objective-terminal-heading[data-select-objective=one]').nextElementSibling.dataset.name==='new-global'`),'one fixed workflow main at top and Objective main immediately after its divider');
 await click('.sess[data-name=workflow-main]');assert(await evaluate('created.length===5'),'workflow main reuses the saved session');
 for(const [status,icon] of [['paused','⏸'],['wont_do','🚫']]){
  await evaluate(`(async()=>{const t=fixture.objectives[0].tasks.find(t=>t.id==='Not started');t.status=${JSON.stringify(status)};fixture.revision+='status';await LabObjectives.load(undefined,true);LabObjectives.renderTasks()})()`);
  assert(await evaluate(`!document.querySelector('.sess[data-name="new-Not started"]')`),'paused and declined terminals hidden by default');
  await click('.objective-sidebar-task [data-open-task="Not started"]');await sleep(80);
  assert(await evaluate(`termCurrentSession==='new-Not started'&&created.length===5&&document.querySelector('.sess[data-name="new-Not started"] .sess-task-status').textContent===${JSON.stringify(icon)}`),'selected paused or declined task reveals its primary and status icon');
 }
 assert(await evaluate('errors.length===0'),'no browser errors with main roles, Show all, paused or declined tasks');
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


def test_main_rows_are_pinned_unique_visible_and_reuse_workflow_creation():
    source = OBJECTIVES.read_text()
    helpers = source[source.index('  function terminalIdentity('):source.index('  function sidebarTarget(')]
    result = _run_node(r'''
const tasks=o=>o?.tasks||[],taskStatus=t=>t.status,taskDisplayName=t=>t.title,taskIcon=()=>'',customTaskIcon=()=>'',esc=String;
const o={id:'one',name:'One',tasks:[{id:'done',title:'Done',status:'done',children:[]}],worktrees:[],resources:[]};
const two={id:'two',name:'Two',tasks:[],worktrees:[]};
const parked={id:'parked',name:'Parked',tasks:[],worktrees:[]};
const registry={enabled:true,focused:['one','two'],objectives:[o,two,parked],terminal_links:{
 duplicate:{objective_id:'one'},main:{objective_id:'one',main:'objective'},done:{objective_id:'one',task_id:'done'},parked:{objective_id:'parked',view:'tasks'}}};
const sessions=['duplicate','done','main','parked'].map(name=>({name,session_id:name,logical_name:name}));
const context=()=>({path:'/workflow',vault:'fixture',workspace_id:'work'}),data=()=>registry,active=()=>true,objective=()=>o,focusedTask=()=>null;
const key=s=>s.vault+'::'+s.workspace_id;
const activated=[],created=[];let finish;
const bridge={workflowName:()=> 'Workflow',sessions:()=>sessions,activateLinkedTerminal:ids=>activated.push(ids),
 createWorkflowTerminal:launch=>{created.push(launch);return new Promise(r=>finish=r)}};
''' + helpers + r'''
const defaults=terminalSessions(sessions),all=terminalSessions(sessions,{wipOnly:false});
const pill=t=>`<tab data-name="${t.name}" data-main="${terminalMain(t)?.kind||''}"></tab>`;
const html=terminalHtml(defaults,pill,'<new>',{arrange:rows=>rows.reverse()}),allHtml=terminalHtml(all,pill,'<new>',{showAll:true});
const parents=terminalParents(all,{main:'done',done:'main'});
(async()=>{
 const a=openMainTerminal('workflow'),b=openMainTerminal('workflow');finish({name:'workflow',session_id:'workflow'});await Promise.all([a,b]);
 sessions.push({name:'workflow',session_id:'workflow',logical_name:'workflow'});registry.terminal_links.workflow={main:'workflow'};
 await openMainTerminal('workflow');
 console.log(JSON.stringify({defaults:defaults.map(s=>s.name),roles:sessions.map(s=>[s.name,terminalMain(s)?.kind||null]),html,allHtml,parents,created,activated}));
})().catch(e=>{console.error(e);process.exit(1)});
''')
    assert result['defaults'] == ['workflow-terminal:work:main', 'main', 'objective-terminal:two:global']
    assert dict(result['roles']) == {'duplicate':None,'done':None,'main':'objective','parked':None,'workflow':'workflow'}
    assert result['parents'] == {}
    assert result['html'].startswith('<tab data-name="workflow-terminal:work:main"')
    assert '</button><tab data-name="main" data-main="objective"></tab><div class="objective-terminal-rows">' in result['html']
    assert '</button><tab data-name="objective-terminal:two:global" data-main="objective"></tab><div class="objective-terminal-rows" hidden>' in result['html']
    assert ' hidden' not in result['allHtml'] and 'data-name="done"' in result['allHtml']
    assert 'data-select-objective="parked"' in result['allHtml'] and 'data-name="parked"' in result['allHtml']
    assert len(result['created']) == 1
    assert result['activated'] == [['workflow'], ['workflow']]
