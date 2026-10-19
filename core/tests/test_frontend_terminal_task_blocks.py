"""Canonical task blocks constrain tab dragging without changing ownership."""
import functools
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import shutil
import subprocess
from threading import Thread
import time

import pytest

from .test_frontend_terminal_ui import _run_node, _js_between
from .test_frontend_terminal_subtabs import OBJECTIVES, GROUPS, MOVES, LAB_SHELL_CSS

HELPERS = '  function terminalIdentity(' + OBJECTIVES.read_text().split('  function terminalIdentity(')[1].split('  function sidebarTarget(')[0]
SETUP = r'''
const _TERM_GROUPS_KEY='groups',_TERM_GROUP_COLORS=['#58a6ff'];
const _termActiveWorkspaceId=()=> 'demo',_termVaultId=()=> 'fixture',_termSessionsKey=(w,v)=>v+'::'+w;
let stored='{}';const localStorage={getItem:()=>stored,setItem:(key,value)=>stored=value};
const task=(id,children=[])=>({id,title:'Same name',status:'in_progress',children});
const a=task('a',[task('child')]),b=task('b');
const o={id:'one',name:'One',tasks:[a,b],worktrees:[],resources:[]};
const two={id:'two',name:'Two',tasks:[task('a')],worktrees:[],resources:[]};
const registry={enabled:true,focused:['one','two'],objectives:[o,two],terminal_links:{
 a1:{objective_id:'one',task_id:'a'},a2:{objective_id:'one',task_id:'a',primary:false},
 inherited:{objective_id:'one',view:'tasks'},child:{objective_id:'one',task_id:'child'},
 b1:{objective_id:'one',task_id:'b'},b2:{objective_id:'one',task_id:'b',primary:false},
 foreign:{objective_id:'two',task_id:'a'},free:{objective_id:'one',view:'tasks'}}};
let termSessions=['a1','b1','child','a2','foreign','b2','inherited','free'].map(name=>({name,logical_name:name,session_id:name,cwd:'/fixed/'+name,agent_session_id:'conversation-'+name,terminal_status:{state:'working'}}));
let termCurrentSession='b1',termCurrentWorkspaceId='demo',_termReorderPending=false;
const context=()=>({workspace_id:'demo',vault:'fixture',path:'/fixture'}),active=()=>true,objective=()=>o,data=()=>registry;
const tasks=o=>o?.tasks.flatMap(t=>[t,...tasks({tasks:t.children})])||[],esc=String;
const taskStatus=t=>t.status,taskDisplayName=t=>t.title,taskIcon=()=>'',customTaskIcon=()=>'',focusedTask=()=>null,state=()=>({});
const bridge={parentTerminal:t=>termSessions.find(parent=>parent.logical_name===_termSubtabParents(_termReadGroupState())[t.logical_name])};
const termSessEsc=String,_termSessionDisplay=s=>s.name,termRenderSessionList=()=>{};
const writes=[];const fetch=async(url,options)=>{writes.push({url,body:JSON.parse(options.body)});return {ok:true}};
const setTimeout=()=>{};
'''
CONNECT = r'''
window.LabObjectives={terminalParents,terminalMain,terminalTaskBlock,taskForTerminal,sameTerminalObjective:(a,b)=>terminalObjective(a)?.id===terminalObjective(b)?.id};
_termWriteGroupState(_termNormalizeGroupState({order:termSessions.map(t=>'s:'+t.name),tabParents:{inherited:'a1'},tabAfter:{a2:'b1',b2:'a1'}}));
const names=()=>{const group=_termReadGroupState();const html=terminalHtml(termSessions,_termSubtabRenderer(group,termSessions,t=>'<tab>'+t.name+'</tab>'),'',{arrange:rows=>_termArrangeSubtabRows(rows,group),showAll:true});return [...html.matchAll(/<tab>(.*?)<\/tab>/g)].map(match=>match[1]);};
'''


def test_blocks_ignore_cross_task_anchors_and_nested_task_parents():
    result = _run_node(SETUP + HELPERS + GROUPS + CONNECT + r'''
const before=JSON.stringify(termSessions),initial=names(),bindings=termSessions.map(t=>terminalTaskBlock(t));
o.tasks.reverse();const moved=names();
console.log(JSON.stringify({initial,moved,bindings,unchanged:before===JSON.stringify(termSessions)}));
''')
    assert result['initial'] == ['free','a1','a2','inherited','child','b1','b2','foreign']
    assert result['moved'] == ['free','b1','b2','a1','a2','inherited','child','foreign']
    assert result['bindings'][0] == result['bindings'][3] == result['bindings'][6]
    assert result['bindings'][0] != result['bindings'][4]
    assert result['unchanged']


def test_members_swap_individually_and_survive_task_moves_and_reload():
    result = _run_node(SETUP + HELPERS + GROUPS + MOVES + CONNECT + r'''
(async()=>{
const identity=JSON.stringify(Object.fromEntries(termSessions.map(t=>[t.name,t]))),assignment=JSON.stringify(registry.terminal_links);
await termReorderItems('s:a1','s:a2',false,'');const swapped=names();
o.tasks.reverse();_termSyncTaskHierarchy(registry);const taskMoved=names();
termSessions.reverse();const reloaded=names();
await termReorderItems('s:inherited','s:a2',true,'');const inheritedMoved=names();
console.log(JSON.stringify({swapped,taskMoved,reloaded,inheritedMoved,parents:_termReadGroupState().tabParents,
sameAssignments:JSON.stringify(registry.terminal_links)===assignment,
unchanged:termSessions.every(t=>JSON.stringify(t)===JSON.stringify(JSON.parse(identity)[t.name])),writes}));
})().catch(e=>{console.error(e);process.exit(1)});
''')
    assert result['swapped'] == ['free','a2','a1','inherited','child','b1','b2','foreign']
    assert result['taskMoved'] == result['reloaded'] == ['free','b1','b2','a2','a1','inherited','child','foreign']
    assert result['inheritedMoved'] == ['free','b1','b2','inherited','a2','a1','child','foreign']
    assert result['parents'] == {'inherited':'a1'}
    assert result['sameAssignments'] and result['unchanged']
    assert all(write['url'] != '/api/objectives' for write in result['writes'])
    assert len([write for write in result['writes'] if write['url'] == '/api/term/sessions/order']) == 2


def test_cross_block_drops_and_group_escape_do_not_write():
    result = _run_node(SETUP + HELPERS + GROUPS + MOVES + CONNECT + r'''
(async()=>{
await _termTaskParentWrites.get('fixture::demo').pending;const before=stored,writeCount=writes.length;
const invalid=[['s:a1','s:b1'],['s:a2','s:foreign'],['s:inherited','s:child'],['s:a1',null],['s:free','s:a1'],['s:a1','s:free'],['s:a1','s:a2',false,'group']];
const results=[];for(const args of invalid)results.push(await termReorderItems(...args));
console.log(JSON.stringify({results,unchanged:stored===before,writes:writes.length-writeCount}));
})().catch(e=>{console.error(e);process.exit(1)});
''')
    assert result['results'] == [False] * 7
    assert result['unchanged'] and result['writes'] == 0


def test_explicit_subterminal_creation_keeps_inherited_membership():
    create = _js_between('  async function _termCreateSubterminal(', '  async function _termLaunchAutomation(')
    result = _run_node(SETUP + HELPERS + GROUPS + MOVES + CONNECT + r'''
const _termSelectedScope=()=>({root:'/fixture'});
window.LabObjectives.childTerminalAssociation=()=>({objective_id:'one',view:'tasks'});
window.LabObjectives.openForTerminal=()=>{};
const termSpawnSession=async(kind,options)=>{
 const row={name:'created',logical_name:'created',session_id:'created',cwd:options.launchChoice.scope.root};
 registry.terminal_links.created={objective_id:'one',view:'tasks'};termSessions.push(row);return row;
};
''' + create + r'''
(async()=>{await _termCreateSubterminal(termSessions.find(t=>t.name==='a1'));
console.log(JSON.stringify({names:names(),block:terminalTaskBlock(termSessions.find(t=>t.name==='created')),parents:_termReadGroupState().tabParents}));
})().catch(e=>{console.error(e);process.exit(1)});
''')
    assert result['names'] == ['free','a1','created','a2','inherited','child','b1','b2','foreign']
    assert result['parents'] == {'inherited':'a1', 'created':'a1'}
    assert result['block'] == '["one","a"]'


@pytest.mark.parametrize('orientation', ['vertical', 'horizontal'])
def test_native_task_and_terminal_block_drags_survive_reload(tmp_path, orientation):
    chrome = os.environ.get('CHROME_BIN') or '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
    if not Path(chrome).is_file() or not shutil.which('node'):
        pytest.skip('Chrome and Node required')
    setup = r'''
let termSessionOrientation=ORIENTATION,termCurrentSession='b1',termCurrentWorkspaceId='demo',_termReorderPending=false;
let _termDragState=null,_termDragLogical=null,_termGroupMenuOutside=null;
const _TERM_GROUPS_KEY='groups',_TERM_GROUP_COLORS=['#58a6ff'];
const _termActiveWorkspaceId=()=> 'demo',_termVaultId=()=> 'fixture',_termSessionsKey=(w,v)=>v+'::'+w;
const termSessEsc=String,_termSessionDisplay=t=>t.name,_termHideSessionTooltip=()=>{},_termClearLinkDropTarget=()=>{};
window.errors=[];addEventListener('error',e=>errors.push(e.error?.stack||e.message));addEventListener('unhandledrejection',e=>errors.push(String(e.reason)));
const task=(id,children=[])=>({id,title:id,status:'in_progress',children,assets:[],action_items:[]});
const initial={enabled:true,task_terminals:false,revision:'1',focused:['one'],terminal_links:{
 a1:{objective_id:'one',task_id:'a'},a2:{objective_id:'one',task_id:'a',primary:false},
 inherited:{objective_id:'one',view:'tasks'},child:{objective_id:'one',task_id:'child'},
 b1:{objective_id:'one',task_id:'b'},b2:{objective_id:'one',task_id:'b',primary:false}},
 objectives:[{id:'one',name:'Project',path:'/workspace/one',color:'#58a6ff',purpose:'',tasks:[task('a',[task('child')]),task('b')],resources:[],worktrees:[],shared_assets:[],unassigned_assets:[],archived_assets:[]}]};
let registry=JSON.parse(localStorage.getItem('registry')||'null')||initial;
let termSessions=JSON.parse(localStorage.getItem('sessions')||'null')||['a1','b1','child','a2','b2','inherited'].map(name=>({name,logical_name:name,session_id:name,cwd:'/fixed/'+name,agent_session_id:'kept-'+name,terminal_status:{state:'working'}}));
const identities=JSON.stringify(Object.fromEntries(termSessions.map(t=>[t.name,t]))),writes=[];
window.fetch=async(url,options={})=>{
 if(options.method==='POST'){
  const body=JSON.parse(options.body);writes.push({url,body});
  if(url==='/api/objectives'){
   const action=body.action;if(action.type!=='task-move')throw Error('Unexpected task mutation '+action.type);
   const o=registry.objectives[0],find=(rows,id)=>rows.flatMap(t=>[t,...find(t.children,id)]).filter(t=>!id||t.id===id);
   const source=find(o.tasks,action.task_id)[0],parent=find(o.tasks).find(t=>t.children.includes(source));
   const old=parent?parent.children:o.tasks;old.splice(old.indexOf(source),1);
   const target=action.parent_id?find(o.tasks,action.parent_id)[0].children:o.tasks,index=target.findIndex(t=>t.id===action.before_id);
   target.splice(index<0?target.length:index,0,source);registry.revision+='!';localStorage.setItem('registry',JSON.stringify(registry));
  }
  if(url==='/api/term/sessions/order')localStorage.setItem('sessions',JSON.stringify(body.order.map(id=>termSessions.find(t=>t.logical_name===id))));
 }
 return {ok:true,json:async()=>structuredClone(registry)};
};
function termRenderSessionList(){const group=_termReadGroupState(),host=document.querySelector('#termSessionList');host.innerHTML=LabObjectives.terminalHtml(termSessions,_termSubtabRenderer(group,termSessions,t=>`<div class="sess" draggable="true" role="tab" data-order-token="s:${t.logical_name}" data-logical="${t.logical_name}" data-name="${t.name}">${t.name}</div>`),'<button id="termNewBtn">+</button>',{arrange:rows=>_termArrangeSubtabRows(rows,group),showAll:true})||'';termWireSessionDnD(host);}
LabObjectives.connect({context:()=>({workspace_id:'demo',vault:'fixture',path:'/workspace'}),scopeRoot:()=>'/workspace',refreshTerminals:termRenderSessionList,sessions:()=>termSessions,session:name=>termSessions.find(t=>[t.name,t.logical_name].includes(name)),
 draggingTerminal:()=>termSessions.find(t=>'s:'+t.logical_name===_termDragLogical),syncTaskHierarchy:_termSyncTaskHierarchy,
 parentTerminal:t=>termSessions.find(p=>p.logical_name===_termSubtabParents(_termReadGroupState())[t.logical_name])});
(async()=>{if(!localStorage.getItem(_TERM_GROUPS_KEY))_termWriteGroupState(_termNormalizeGroupState({order:termSessions.map(t=>'s:'+t.name),tabParents:{inherited:'a1'},tabAfter:{a2:'b1'}}));await LabObjectives.load();LabObjectives.renderTasks();termRenderSessionList();document.body.dataset.ready='true';})();
'''.replace('ORIENTATION', repr(orientation))
    css = LAB_SHELL_CSS.read_text() + (LAB_SHELL_CSS.parent / 'workspace-objectives.css').read_text()
    page = '<!doctype html><meta charset="utf-8"><style>'+css+'''
body{background:#181c20;color:white;font:16px sans-serif}#content{width:460px}#sidebar{width:460px}#termSessionList{position:fixed;left:520px;top:30px;width:700px}.sess{display:block;width:120px;min-height:40px;margin:3px;background:#35404a;border:1px solid white;cursor:grab}.objective-terminal-worktree{display:contents}.objective-terminal-rows{display:LAYOUT}.objective-task-row{min-height:40px}.objective-terminal-heading{color:white}
</style><body><aside id="sidebar"><section data-objectives-sidebar></section></aside><main id="content"></main><div id="termSessionList" class="term-sessions"></div><div id="termGroupMenu" hidden></div><script>'''.replace('LAYOUT','flex;flex-wrap:wrap' if orientation=='horizontal' else 'block')+OBJECTIVES.read_text()+GROUPS+MOVES+setup+'</script>'
    (tmp_path / 'fixture.html').write_text(page)
    class Handler(SimpleHTTPRequestHandler):
        def log_message(self, *args): pass
    server = ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Handler,directory=str(tmp_path)))
    Thread(target=server.serve_forever,daemon=True).start()
    profile=tmp_path/'chrome'
    process=subprocess.Popen([chrome,'--headless=new','--no-first-run','--remote-debugging-port=0','--user-data-dir='+str(profile),'about:blank'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    driver=r'''
const fs=require('node:fs');
(async()=>{
 const assert=(v,m)=>{if(!v)throw Error(m)},sleep=ms=>new Promise(r=>setTimeout(r,ms));
 const [port]=fs.readFileSync(process.argv[1]+'/DevToolsActivePort','utf8').split('\n');
 const tab=await fetch(`http://127.0.0.1:${port}/json/new?about:blank`,{method:'PUT'}).then(r=>r.json());
 const ws=new WebSocket(tab.webSocketDebuggerUrl),pending=new Map();let seq=0,dragData;
 ws.onmessage=e=>{const m=JSON.parse(e.data);if(m.method==='Input.dragIntercepted')dragData=m.params.data;if(m.id){const p=pending.get(m.id);pending.delete(m.id);m.error?p.reject(Error(m.error.message)):p.resolve(m.result)}};
 await new Promise(r=>ws.addEventListener('open',r,{once:true}));
 const send=(method,params={})=>new Promise((resolve,reject)=>{const id=++seq;pending.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}))});
 async function evaluate(expression){const r=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(r.exceptionDetails)throw Error(r.exceptionDetails.exception?.description||'Browser exception');return r.result.value;}
 const ready=async()=>{for(let i=0;i<150;i++){if(await evaluate('document.body?.dataset.ready==="true"'))return;await sleep(20)}throw Error('Startup: '+await evaluate('errors.join("\\n")'))};
 const names=()=>evaluate(`[...document.querySelectorAll('#termSessionList .sess')].map(n=>n.dataset.name).join(',')`);
 async function drag(source,target,before=false){
  const point=async(selector,destination=false)=>evaluate(`(()=>{const n=document.querySelector(${JSON.stringify(selector)});if(!n)throw Error('Missing '+${JSON.stringify(selector)});n.scrollIntoView({block:'nearest'});const r=n.getBoundingClientRect(),fraction=${before?'.2':'.8'};return {x:r.x+r.width*(termSessionOrientation==='horizontal'&&${destination} ?fraction:.5),y:r.y+r.height*(termSessionOrientation!=='horizontal'||!${JSON.stringify(target)}.startsWith('.sess')?fraction:.5)}})()`);
  const a=await point(source),b=await point(target,true);dragData=null;await send('Input.setInterceptDrags',{enabled:true});
  await send('Input.dispatchMouseEvent',{type:'mouseMoved',...a});await send('Input.dispatchMouseEvent',{type:'mousePressed',...a,button:'left',buttons:1,clickCount:1});
  await send('Input.dispatchMouseEvent',{type:'mouseMoved',x:a.x+25,y:a.y+3,button:'left',buttons:1});for(let i=0;i<100&&!dragData;i++)await sleep(10);assert(dragData,'trusted drag starts');
  const count=await evaluate('writes.length');for(const type of ['dragEnter','dragOver','dragOver'])await send('Input.dispatchDragEvent',{type,...b,data:dragData});
  assert(await evaluate('writes.length')===count,'preview does not write');await send('Input.dispatchDragEvent',{type:'drop',...b,data:dragData});
  await send('Input.dispatchMouseEvent',{type:'mouseReleased',...b,button:'left',clickCount:1});await send('Input.setInterceptDrags',{enabled:false});await sleep(60);
 }
 await send('Emulation.setDeviceMetricsOverride',{width:1500,height:1000,deviceScaleFactor:1,mobile:false});await send('Page.navigate',{url:process.argv[2]});await ready();
 assert(await names()==='a1,a2,inherited,child,b1,b2','initial blocks ignore stale cross-block positions');
 await drag('.sess[data-name=a1]','.sess[data-name=a2]');assert(await names()==='a2,a1,inherited,child,b1,b2','same-block drop swaps one terminal directly');
 assert(await evaluate(`document.getElementById('termGroupMenu').hidden&&registry.objectives[0].tasks[0].id==='a'`),'tab swap opens no chooser and moves no task');
 const saved=await evaluate('JSON.stringify({stored:localStorage.getItem(_TERM_GROUPS_KEY),writes:writes.length})');
 await drag('.sess[data-name=a2]','.sess[data-name=b1]');assert(await evaluate('JSON.stringify({stored:localStorage.getItem(_TERM_GROUPS_KEY),writes:writes.length})')===saved,'cross-task tab drop makes no writes');
 await drag('.sess[data-name=a2]','[data-objective-tasks-drop]');assert(await evaluate('JSON.stringify({stored:localStorage.getItem(_TERM_GROUPS_KEY),writes:writes.length})')===saved,'Tasks header cannot move a task through its terminal');
 await drag('.objective-sidebar-task [data-open-task=b]','.objective-sidebar-task[data-task-id=a]',true);
 assert(await names()==='b1,b2,a2,a1,inherited,child','task drag moves whole block and retains member order');
 assert(await evaluate(`!document.querySelector('.objective-dialog')&&writes.filter(w=>w.url==='/api/objectives').length===1`),'normal task drag reorders immediately with one task mutation');
 await drag('.sess[data-name=inherited]','.sess[data-name=a2]',true);assert(await names()==='b1,b2,inherited,a2,a1,child','inherited member reorders individually: '+await names()+' '+await evaluate('JSON.stringify({state:_termReadGroupState(),errors,writes})'));
 await evaluate(`document.body.dataset.ready='false'`);await send('Page.reload');await ready();
 assert(await names()==='b1,b2,inherited,a2,a1,child','task and internal tab orders survive a full reload');
 assert(await evaluate(`termSessions.every(t=>JSON.stringify(t)===JSON.stringify(JSON.parse(identities)[t.name]))&&_termReadGroupState().tabParents.inherited==='a1'&&errors.length===0`),'sessions, conversations, status and inheritance stay intact');
 fs.writeFileSync(process.argv[1]+'/../task-blocks.png',Buffer.from((await send('Page.captureScreenshot',{format:'png'})).data,'base64'));ws.close();console.log('PASS');
})().catch(e=>{console.error(e.stack);process.exit(1)});
'''
    try:
        deadline=time.monotonic()+10
        while not (profile/'DevToolsActivePort').exists():
            assert process.poll() is None and time.monotonic()<deadline, 'Chrome did not start'
            time.sleep(.05)
        result=subprocess.run(['node','-e',driver,str(profile),f'http://127.0.0.1:{server.server_port}/fixture.html'],capture_output=True,text=True,timeout=45)
        assert result.returncode==0,result.stdout+result.stderr
    finally:
        process.terminate();process.wait(timeout=10);server.shutdown();server.server_close()
