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
const tasks=o=>o?.tasks.flatMap(t=>[t,...t.children])||[],taskIcon=()=>'<icon>',customTaskIcon=()=>'',taskStatus=()=> 'todo',esc=String;
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
window.LabObjectives={terminalParents,terminalExpanded,sameTerminalObjective:(a,b)=>terminalObjective(a)?.id===terminalObjective(b)?.id};
const augmented=terminalSessions(termSessions),parents=_termSubtabParents(group,augmented);
const missing=augmented.find(t=>t.task_id==='missing'),binding=terminalTask(termSessions[4]);
const original=JSON.stringify(registry.terminal_links);
openForTerminal(termSessions[4]);const expanded=terminalExpanded(termSessions[1]);
''' + MOVES + r'''
const moved=_termPlanItemMove(group,'s:subtask','s:global',false,'','below');
(async()=>{
 await openTaskTerminal('parent');await openTaskTerminal(null);
 const first=openTaskTerminal('missing'),second=openTaskTerminal('missing');
 finishCreate({name:'new-terminal'});await Promise.all([first,second]);
 console.log(JSON.stringify({parents,missing,binding:{id:binding.task.id,inherited:binding.inherited},expanded,
 opened,created,activated,manualParents:_termSubtabParents(moved,augmented),manualRoots:moved.tabRoots,
 ownTask:taskForTerminal(termSessions[1]),extraTask:taskForTerminal(termSessions[4]),unchanged:original===JSON.stringify(registry.terminal_links)}));
})().catch(e=>{console.error(e);process.exit(1)});
''')
    assert result['parents'] == {'subtask': 'parent', 'extra': 'subtask', 'grandchild': 'extra'}
    assert result['missing']['objective_placeholder'] and result['missing']['label'] == 'missing'
    assert result['binding'] == {'id': 'subtask', 'inherited': True}
    assert result['expanded'] and result['opened'][0] == 'subtask'
    assert result['ownTask']['title'] == 'parent' and not result['ownTask']['inherited']
    assert result['extraTask']['title'] == 'subtask' and result['extraTask']['inherited']
    assert result['activated'] == [['parent'], ['global']]
    assert len(result['created']) == 1 and result['created'][0]['task']['id'] == 'missing'
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
let termSessionOrientation=ORIENTATION;
let termSessions=['a','b','c','other'].map(name=>({name,logical_name:name,session_id:'uuid-'+name,cwd:'/workspace',kind:'terminal'}));
const originalSessions=JSON.stringify(termSessions),mutations=[];
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
const fixture={enabled:true,revision:'fixture',focused:['one','two','empty'],terminal_links:Object.fromEntries(termSessions.map(s=>[s.session_id,{objective_id:s.name==='other'?'two':'one'}])),objectives:['one','two','empty'].map((id,i)=>({id,name:id,color:['#58a6ff','#bc8cff','#ffa657'][i],path:'/workspace/'+id,purpose:'',tasks:[],resources:[],worktrees:[],shared_assets:[],unassigned_assets:[],archived_assets:[]}))};
window.fetch=async(url,options={})=>{if(options.method==='POST'){mutations.push(JSON.parse(options.body));return{ok:true,json:async()=>({})};}return{ok:true,json:async()=>structuredClone(fixture)}};
window.errors=[];window.addEventListener('error',e=>errors.push(e.error?.stack||e.message));window.addEventListener('unhandledrejection',e=>errors.push(String(e.reason)));
const created=[];
LabObjectives.connect({context:()=>({workspace_id:workspace,vault,path:'/workspace'}),refreshTabs:()=>document.querySelector('.repo-tabs').innerHTML=LabObjectives.tabsHtml('/workspace'),refreshTerminals:()=>termRenderSessionList(),prepareCenter:()=>{},scopeRoot:()=>'/workspace',
 sessions:()=>termSessions,parentTerminal:t=>termSessions.find(p=>p.logical_name===_termSubtabParents(_termReadGroupState(),termSessions)[t.logical_name]),
 activateLinkedTerminal:ids=>{const t=termSessions.find(t=>ids.includes(t.session_id));if(t)_termActivateTab(t.name);},
 createTaskTerminal:async(launch,task)=>{created.push({launch,task});const name='new-'+(task?.id||'global'),session={name,logical_name:name,session_id:'uuid-'+name,cwd:launch.path,kind:'terminal'};
 termSessions.push(session);fixture.terminal_links[session.session_id]={objective_id:launch.id,...(task?{task_id:task.id}:{})};fixture.revision+='!';await LabObjectives.load(undefined,true);await _termActivateTab(name);return session;}});
(async()=>{await LabObjectives.load();LabObjectives.openCurrent();termRenderSessionList();document.body.dataset.ready='true'})();
'''.replace('ORIENTATION', repr(orientation))
    css = LAB_SHELL_CSS.read_text() + (LAB_SHELL_CSS.parent / 'workspace-objectives.css').read_text()
    page = '<!doctype html><meta charset="utf-8"><style>'+css+' .term-panel{width:680px}.term-tabs-open{--term-sessions-width:230px}#content{width:calc(100vw - 680px)}</style><body class="term-open"><button id="outside">Outside</button><div class="repo-tabs"></div><main id="content"></main><section class="term-panel term-sessions-full '+('term-sessions-horizontal' if orientation=='horizontal' else '')+'"><div class="term-stage"><div class="term-session-switcher term-tabs-open"><div class="term-sessions" id="termSessionList"></div></div></div></section><div id="termGroupMenu" class="term-group-menu" hidden></div><script>'+OBJECTIVES.read_text()+'</script><script>'+GROUPS+MOVES+RENDER+PILL+setup+'</script>'
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
 const point=async selector=>evaluate(`(()=>{const n=document.querySelector(${JSON.stringify(selector)});if(!n?.getClientRects().length)throw Error('Invisible '+${JSON.stringify(selector)});n.scrollIntoView({block:'nearest'});const r=n.getBoundingClientRect();return{x:r.x+r.width/2,y:r.y+r.height/2}})()`);
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
 await click(tab('a'));
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
 const o=fixture.objectives[0],makeTask=(id,children=[])=>({id,title:id,children,done:false,status:'todo',document_id:'details',tab_id:id,assets:[]});
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
