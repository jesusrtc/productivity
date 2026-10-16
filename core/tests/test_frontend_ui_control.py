"""Real CLI → HTTP → authenticated browser → shared mutation end to end."""
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
from threading import Thread
import time

from fastapi.responses import HTMLResponse
import pytest
import uvicorn

from lab import objectives
from core import link_services
from .test_term_routes import isolated_prefix  # noqa: F401
from .test_terminal_automations import _save

STATIC=Path(__file__).resolve().parents[1]/'src/core/static'


def test_cli_operates_link_modal_drag_workspace_terminal_label_and_automation(client,monorepo,seed_workspace,tmp_path,isolated_prefix):
    chrome=os.environ.get('CHROME_BIN') or shutil.which('chromium') or '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
    if not Path(chrome).is_file() or not shutil.which('node'):
        pytest.skip('Chrome and Node required')
    folder=seed_workspace()
    data=objectives.mutate(monorepo,'demo',{'type':'create','name':'CLI project'})
    oid=data['objectives'][0]['id']
    data=objectives.mutate(monorepo,'demo',{'type':'resource','objective_id':oid,'kind':'link','title':'Reference','url':'https://example.com/original'})
    rid=data['objectives'][0]['resources'][0]['id']
    objectives.mutate(monorepo,'demo',{'type':'asset-star','objective_id':oid,'resource_id':rid,'starred':True})
    data=objectives.mutate(monorepo,'demo',{'type':'task','objective_id':oid,'title':'CLI task'})
    tid=data['objectives'][0]['tasks'][0]['id']
    data=objectives.mutate(monorepo,'demo',{'type':'resource','objective_id':oid,'kind':'notebook','title':'Linked analysis'})
    nid=data['objectives'][0]['resources'][-1]['id']
    objectives.mutate(monorepo,'demo',{'type':'asset-star','objective_id':oid,'resource_id':nid,'starred':True})
    from core.routes import term
    term._upsert_workspace_session(monorepo,'demo',{'name':'ui-shell','kind':'terminal','cwd':str(folder)})
    term._upsert_workspace_session(monorepo,'demo',{'name':'ui-task','kind':'terminal','cwd':str(folder)})
    objectives.mutate(monorepo,'demo',{'type':'terminal','objective_id':oid,'task_id':tid,'session_id':'ui-task'})
    _save(client,'demo',[{'label':'First defined','command':'printf first'}, {'label':'Second defined','command':'printf second'}])
    app_source=(STATIC/'js/lab-app.js').read_text()
    terminal_visual=app_source[app_source.index('  function _termSessionVisual('):app_source.index('  function _termSessionIsWorking(')]
    terminal_pill=app_source[app_source.index('  function _termTaskStatusLabel('):app_source.index('  function _termTaskPlaceholderHtml(')]
    file_icon=app_source[app_source.index('  function fileIconHtml('):app_source.index('  function buildSidebarTree(')]
    terminal_create=app_source[app_source.index('  function termCreateNew('):app_source.index('  async function termKillCurrent(')]
    automation_launch=app_source[app_source.index('  async function _termLaunchAutomation('):app_source.index('  async function _termPasteTaskContext(')]
    primary_action=app_source[app_source.index('  const _termPrimaryChanges ='):app_source.index('  function _termSubtabRenderer(')]
    tab_menu=app_source[app_source.index('  function termOpenTabMenu('):app_source.index('  function termOpenSelectedTabsMenu(')]
    close_tabs=app_source[app_source.index('  const _termCloseTabsPending'):app_source.index('  function _termSessionDisplay(s)')]
    new_automation=next(line for line in (STATIC.parent/'templates/index.html').read_text().splitlines() if 'id="termNewAutomation"' in line)
    patch_links=app_source[app_source.index('  async function _termPatchLinks('):app_source.index('  window.LabTaskTerminalBridge =')]
    navigation=app_source[app_source.index('  function goToWorkspace('):app_source.index('  // Navigate to a workspace by its id')]
    resize_start=app_source.index('  function _termInitSessionResize()')
    resize=app_source[resize_start:app_source.index('\n  }\n',resize_start)+5]
    hooks=app_source[app_source.index('  if(LAB_IS_ADMIN)window.LabUiControl?.start('):]
    setup=r'''
const LAB_IS_ADMIN=true,currentVaultId=null;let currentWorkspace={name:'demo',path:FIX.folder,is_workspace:true},workspacesList=[currentWorkspace],_workspaceDocPath=null;
const _workspaceVaultId=()=>null,_swapViewState=()=>{},_settleWorkspaceHistory=()=>{},fetchRepos=async()=>workspacesList;
const selectRepo=async path=>{currentWorkspace=workspacesList.find(w=>w.path===path);document.querySelector('#view-status').textContent=path;};
let termSessions=[{name:'ui-shell-live',logical_name:'ui-shell',label:null,state:'running'},{name:'ui-task-live',logical_name:'ui-task',session_id:'ui-task',state:'running'}];
let termCurrentSession='ui-shell-live';const termCurrentWorkspaceId='demo',requestSubmissions=[],_termRequestSubmitted=(...parts)=>requestSubmissions.push(parts);const pasted=[],sent=[],termXterm={modes:{bracketedPasteMode:true},paste:text=>pasted.push(text)},termWS={readyState:WebSocket.OPEN,send:value=>sent.push(JSON.parse(value))},_termActivateTab=async name=>{termCurrentSession=name};
const _termLinkContext=()=>({workspaceId:'demo',vaultId:null}),_termActiveWorkspaceId=()=> 'demo',_termVaultId=()=>null;
const _termSessionsCache=new Map(),_termSessionsKey=(w,v)=>w+'::'+v,termRenderSessionList=()=>document.querySelector('#terminal-label').textContent=termSessions[0].label||'Shell',_termRenderActiveSessionHeader=()=>{};
let termSessionWidth=180,termSessionOrientation='vertical';const _TERM_SESSION_WIDTH_KEY='cli-test-width',_termSessionWidthBounds=()=>({min:160,max:220}),_termApplySessionView=()=>{document.querySelector('#termSessionList').style.width=termSessionWidth+'px'};
let automationGroup={order:[],tabParents:{},tabRoots:[],tabAfter:{},tabMembership:{},tabGroups:[],tabDisplayMains:{}};
const _termGroupScopeKey=()=>_termSessionsKey('demo',null),_termReadGroupState=()=>structuredClone(automationGroup),_termWriteGroupState=state=>{automationGroup=state};
const _termHomeSection=()=>null,_termInvalidateSessionReads=()=>{},termSetAutoSpawnEnabled=async()=>{};
let _termRefreshSessionsForWorkspaceId=async()=>{};
const _vaultQuery=()=>'',_termEvictCache=()=>{},termDetach=()=>{termCurrentSession=null;},termShowEmpty=()=>{};
window.LabSettingsBridge={currentScope:()=>({id:'demo',path:FIX.folder,label:'Demo',vault:null})};
const termSessEsc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const _termSessionDisplay=s=>s.label||s.logical_name,_termSessionRecentMeta=()=>null,_termSessionIsWorking=()=>false,_termSessionSummary=()=>'',_termSessionTooltipPayload=()=> '{}',_termSessionContext=()=>({label:'Requests'}),_termSessionAssociationHtml=()=>'',_termRecentScopeKey=()=> 'demo',termDeadSessions=new Set(),_termSubtabParents=()=>automationGroup.tabParents;
const _termSessionMeta=name=>termSessions.find(s=>s.name===name),_termSessionLogical=name=>_termSessionMeta(name)?.logical_name;
const _termSelectTab=()=>{},_termTabSelection=()=>[],_termDisplayMains=()=>new Map();
const termCloseGroupMenu=()=>document.querySelector('#terminal-menu-items').replaceChildren();
const _termShowGroupMenu=(anchor,html,callback)=>{const host=document.querySelector('#terminal-menu-items');host.innerHTML=html;host.querySelectorAll('[data-action]').forEach(button=>button.onclick=()=>callback(button.dataset.action));};
const _sidebarFileConfigScope='fixture',_sidebarFileConfig={},_workspaceDisplayName=()=> 'Demo';
const _termSelectedScope=()=>({root:FIX.folder}),_termClearDead=()=>{},termSetStatus=()=>{};
const termAttach=name=>_termActivateTab(name),termRefreshSessions=async()=>{},termRefreshSessionsByWorkspaceId=async()=>{};
const CEREBRO_WORKSPACE_ID='__cerebro__',SELF_WORKSPACE_ID='__self__',ASSISTANT_WORKSPACE_ID='__assistant__';
const assetOpened=[];
window.explorerToast=message=>{document.querySelector('#notice').textContent=message};
window.LabExternalLinks={open:url=>{assetOpened.push(url);return Promise.resolve(true)}};
LabObjectives.connect({context:()=>({workspace_id:'demo',path:FIX.folder}),refreshTabs:()=>{},readyContent:()=>Promise.resolve(),prepareCenter:()=>{},
 activeTerminal:()=>termSessions.find(t=>t.name===termCurrentSession),session:name=>termSessions.find(t=>t.name===name),fileIcon:fileIconHtml,openNotebook:r=>assetOpened.push(r.id),
 parentTerminal:t=>termSessions.find(p=>p.logical_name===automationGroup.tabParents[t.logical_name]),
 sessions:()=>termSessions,activateLinkedTerminal:ids=>{const terminal=termSessions.find(t=>ids.includes(t.session_id||t.name));if(terminal)return _termActivateTab(terminal.name);}});
LabObjectives.load().then(()=>LabObjectives.selectObjective(FIX.oid));
'''
    page='<!doctype html><meta charset="utf-8"><style>'+(STATIC/'css/workspace-objectives.css').read_text()+'body{background:#0d1117;color:white;display:flex}#sidebar{width:350px}#content{flex:1}</style><body class="workspace-active"><aside id="sidebar"><section data-objectives-sidebar></section></aside><main id="content"></main><section><button id="tasks" onclick="LabObjectives.renderTasks()">Tasks</button><button id="native" onclick="const value=prompt(\'Name\');if(value!==null)document.querySelector(\'#native-value\').textContent=value">Native prompt</button><span id="native-value"></span><span id="terminal-label">Shell</span><span id="view-status"></span><p id="notice"></p></section>'
    page+='<script>const FIX='+json.dumps({'folder':str(folder),'oid':oid,'nid':nid})+';</script>'
    page+='<script>window.LAB_LINK_SERVICES='+json.dumps(link_services.SERVICES)+';</script>'
    page+=''.join('<script>'+(STATIC/'js/lib'/name).read_text()+'</script>' for name in ('scope-links.js','workspace-objectives.js','terminal-folder.js','terminal-automations.js','ui-control.js'))
    page+='<button id="new-task-terminal" onclick="termCreateNew(\'terminal\')">New terminal</button>'
    page+='<button id="terminal-menu" onclick="termOpenTabMenu(termCurrentSession,this)">Terminal menu</button><div id="terminal-menu-items"></div>'
    page+='<button id="asset-picker" onclick="LabObjectives.chooseTerminalAsset(termSessions.find(t=>t.name===termCurrentSession))">Link to asset…</button>'
    page+='<div id="termNewPicker">'+new_automation+'</div>'
    page+='<div id="termPanel"><div id="termSessionSwitcher" class="term-tabs-open"><div id="termSessionList" style="width:180px">Terminal rail</div><div id="termSessionsResizer" role="separator" tabindex="0" aria-label="Resize terminal tabs" style="width:5px;height:30px"></div></div></div>'
    page+='<script>'+file_icon+setup+patch_links+navigation+resize+automation_launch+terminal_create+primary_action+tab_menu+close_tabs+terminal_visual+terminal_pill+'_termInitSessionResize();'+hooks+'</script>'
    app=client.app
    @app.get('/_cli-test',include_in_schema=False)
    def fixture_page(): return HTMLResponse(page)
    listener=socket.socket();listener.bind(('127.0.0.1',0))
    base=f'http://127.0.0.1:{listener.getsockname()[1]}'
    server=uvicorn.Server(uvicorn.Config(app,log_level='critical',lifespan='off'))
    thread=Thread(target=lambda:server.run(sockets=[listener]),daemon=True);thread.start()
    profile=tmp_path/'chrome'
    process=subprocess.Popen([chrome,'--headless=new','--no-first-run','--remote-debugging-port=0','--user-data-dir='+str(profile),'about:blank'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    driver=r'''
const fs=require('node:fs'),{execFileSync}=require('node:child_process');
(async()=>{
 const [port]=fs.readFileSync(process.argv[1]+'/DevToolsActivePort','utf8').split('\n');
 const target=await fetch(`http://127.0.0.1:${port}/json/new?about:blank`,{method:'PUT'}).then(r=>r.json());
 const ws=new WebSocket(target.webSocketDebuggerUrl),pending=new Map();let seq=0;
 ws.onmessage=e=>{const m=JSON.parse(e.data);if(m.id){const p=pending.get(m.id);pending.delete(m.id);m.error?p.reject(Error(m.error.message)):p.resolve(m.result)}};
 await new Promise(r=>ws.addEventListener('open',r,{once:true}));
 const send=(method,params={})=>new Promise((resolve,reject)=>{const id=++seq;pending.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}))});
 const evaluate=async expression=>{const r=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(r.exceptionDetails)throw Error(r.exceptionDetails.exception?.description);return r.result.value};
 const cli=(...args)=>JSON.parse(execFileSync(process.argv[3],['-m','lab',...args],{encoding:'utf8',env:{...process.env,LAB_URL:process.argv[2]}}));
 const assert=(v,m)=>{if(!v)throw Error(m)};
 await send('Page.navigate',{url:process.argv[2]+'/login'});
 for(let i=0;i<100;i++){if(await evaluate(`location.pathname==='/login'&&document.readyState==='complete'`))break;await new Promise(r=>setTimeout(r,30));}
 await evaluate(`fetch('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:'admin',password:'admin'})}).then(r=>{if(!r.ok)throw Error('login')})`);
 await send('Page.navigate',{url:process.argv[2]+'/_cli-test'});
 let view;
 for(let i=0;i<200;i++){view=cli('ui','clients').find(c=>c.url.endsWith('/_cli-test'));if(view&&await evaluate(`!!document.querySelector('[data-objective-resource]')`))break;await new Promise(r=>setTimeout(r,30));}
 assert(view,'registered browser view');
 const ui=(...args)=>cli('ui','--client',view.id,...args);
 const inspect=()=>ui('inspect');
 const control=label=>{const row=inspect().controls.find(c=>c.label===label);assert(row,'control '+label);return row.selector};
 ui('contextmenu','[data-objective-bucket=objective] [data-objective-resource="'+process.argv[4]+'"]');
 assert(control('Copy URL')&&control('Open in Chrome'),'URL actions are discoverable through CLI');
 ui('click',control('Edit'));
 assert(inspect().dialogs.some(d=>d.title==='Edit link'),'CLI opens real modal');
 ui('fill','[data-objective-link-field=url]','https://example.com/cli-edited');
 ui('click','[data-save-objective-link]');ui('wait','[data-link-details-status]','--text','Saved');
 let data=cli('api','call','GET','/api/objectives','--query','workspace_id=demo');
 assert(data.objectives[0].resources.find(r=>r.id===process.argv[4]).url==='https://example.com/cli-edited','same saved resource');
 ui('key','Escape');assert(!inspect().dialogs.length,'CLI Escape closes modal');
 let promptResult=ui('click','#native');assert(promptResult.native_dialogs[0].requires_answer,'unanswered prompt returns without blocking');
 ui('click','#native','--prompt','CLI name');assert(await evaluate(`document.querySelector('#native-value').textContent==='CLI name'`),'prompt answer is scoped to the action');
 ui('rename-tab','ui-shell','Review renamed');assert(await evaluate(`document.querySelector('#terminal-label').textContent==='Review renamed'`),'terminal rename uses real shared metadata handler');
 ui('paste','First line\nSecond line','--terminal','ui-shell');assert(await evaluate(`pasted.at(-1)==='First line\\nSecond line'&&sent.length===0`),'terminal paste retains bracketed text without submitting');
 await evaluate(`termXterm.modes.bracketedPasteMode=false`);ui('paste','One\nTwo');assert(await evaluate(`pasted.at(-1)==='One Two'&&sent.length===0`),'unbracketed multiline paste stays unsent');
 ui('paste','Explicit command','--submit');assert(await evaluate(`sent.length===1&&sent[0].data==='\\r'&&requestSubmissions.length===1&&requestSubmissions[0][1]==='demo'`),'only explicit submit sends Enter');
 ui('command','pointer-drag','--json',JSON.stringify({selector:'#termSessionsResizer',x:20,y:0}));assert(await evaluate(`termSessionWidth===200&&localStorage.getItem(_TERM_SESSION_WIDTH_KEY)==='200'`),'CLI resize uses and saves the real terminal rail handler');
 ui('click','#tasks');ui('drag','[data-objective-bucket=objective] [data-objective-resource="'+process.argv[4]+'"]','.objective-task-row[data-task-id="'+process.argv[5]+'"]');
 for(let i=0;i<100;i++){data=cli('api','call','GET','/api/objectives','--query','workspace_id=demo');if(data.objectives[0].tasks[0].assets?.some(a=>a.resource_id===process.argv[4]))break;await new Promise(r=>setTimeout(r,30));}
 assert(data.objectives[0].tasks[0].assets.some(a=>a.resource_id===process.argv[4]),'CLI drag uses task asset drop handler');
 const task=process.argv[5],objective=data.objectives[0].id;
 const status=value=>cli('api','call','POST','/api/objectives','--json',JSON.stringify({workspace_id:'demo',action:{type:'task-update',objective_id:objective,task_id:task,status:value}}));
 const openTask=()=>ui('command','task-open','--json',JSON.stringify({task,objective}));
 const shown=()=>evaluate(`LabObjectives.terminalSessions(termSessions).some(t=>t.logical_name==='ui-task')`);
 openTask();assert(await evaluate(`termCurrentSession==='ui-shell-live'&&LabObjectives.terminalLaunchContext().task.id===${JSON.stringify(task)}`)&&!await shown(),'CLI opens Todo details without revealing or activating its terminal');
 status('in_progress');openTask();
 assert(await evaluate(`termCurrentSession==='ui-task-live'`)&&await shown(),'CLI task opening reuses its In progress terminal like a normal click');
 ui('command','terminal-select','--json',JSON.stringify({name:'ui-shell'}));
 status('paused');openTask();
 assert(await evaluate(`termCurrentSession==='ui-shell-live'`)&&!await shown(),'CLI paused-task navigation respects the terminal status filter');
 ui('click','a.objective-sidebar-task-title[data-open-task="'+task+'"]');
 assert(await evaluate(`termCurrentSession==='ui-shell-live'`)&&!await shown(),'normal paused-task click agrees with CLI navigation');
 status('in_progress');await evaluate(`LabObjectives.load(undefined,true)`);
 ui('click','a.objective-sidebar-task-title[data-open-task="'+task+'"]');
 assert(await evaluate(`termCurrentSession==='ui-task-live'`)&&await shown(),'resuming restores the same linked terminal through a normal click');
 // The CLI discovers and operates the same + New action, with real API ownership.
 ui('click',control('Launch automation…'));
 ui('wait','#termAutomationLauncher [data-preview]','--text','First defined · Primary');
 assert(await evaluate(`document.querySelector('#termAutomationLauncher').textContent.includes('CLI task')`),'launcher captures the active task');
 ui('click','#termAutomationLauncher [data-launch]');
 const launchDeadline=Date.now()+12000; // Includes the default five-second interval.
 while(Date.now()<launchDeadline){if(await evaluate(`!document.querySelector('#termAutomationLauncher')`))break;await new Promise(r=>setTimeout(r,30));}
 assert(await evaluate(`(()=>{const rows=termSessions.filter(s=>s.logical_name.startsWith('automation-')),task=LabObjectives.taskForTerminal(rows[0]);return rows.length===2&&rows[0].label==='First defined'&&termCurrentSession===rows[0].name&&!automationGroup.tabParents[rows[0].logical_name]&&automationGroup.tabParents[rows[1].logical_name]===rows[0].logical_name&&task?.title==='CLI task'&&!task.inherited})()`),'CLI launch creates exactly its recipe terminals, activates first and nests second');
 const launched=await evaluate(`termSessions.filter(s=>s.logical_name.startsWith('automation-'))`);
 data=cli('api','call','GET','/api/objectives','--query','workspace_id=demo');
 assert(data.terminal_links[launched[0].session_id].task_id===task&&!data.terminal_links[launched[1].session_id].task_id&&data.terminal_links['ui-task'].task_id===task&&data.terminal_links['ui-task'].primary===false,'API persists new primary without removing old terminal');
 const original=JSON.stringify(data.terminal_links[launched[0].session_id]);
 const github='https://github.com/example/repo/issues/7';
 cli('api','call','POST','/api/objectives','--json',JSON.stringify({workspace_id:'demo',action:{type:'link-update',objective_id:objective,resource_id:process.argv[4],title:'Reference',url:github}}));
 await evaluate(`LabObjectives.load(undefined,true)`);
 ui('contextmenu','[data-objective-bucket=objective] [data-objective-resource="'+process.argv[4]+'"]');
 ui('click',control('Link to active terminal'));
 ui('wait','#notice','--text','Terminal linked.');
 data=cli('api','call','GET','/api/objectives','--query','workspace_id=demo');
 const linked=data.terminal_links[launched[0].session_id],{asset,...origin}=linked;
 assert(JSON.stringify(origin)===original&&asset.resource_id===process.argv[4],'link keeps the automation primary and its task origin');
 assert(await evaluate(`(()=>{const t=termSessions.find(s=>s.name===termCurrentSession),holder=document.createElement('div');holder.innerHTML=_termSessionPillHtml(t,0);return holder.querySelector('.sess-icon [data-link-service=github]')&&_termSessionVisual(t).icon.includes('github')})()`),'GitHub icon wins in automation pill and active header visual');
 ui('command','terminal-select','--json',JSON.stringify({name:'ui-shell'}));
 ui('click','[data-objective-bucket=objective] [data-objective-resource="'+process.argv[4]+'"]');
 assert(await evaluate(`termCurrentSession===${JSON.stringify(launched[0].name)}&&assetOpened.at(-1)===${JSON.stringify(github)}`),'asset click opens the link and activates its terminal');
 const count=await evaluate('assetOpened.length');
 ui('command','terminal-select','--json',JSON.stringify({name:launched[0].name}));
 assert(await evaluate(`assetOpened.length===${count+1}&&assetOpened.at(-1)===${JSON.stringify(github)}&&LabObjectives.terminalLaunchContext().task.id===${JSON.stringify(task)}`),'reverse navigation opens the exact asset while retaining task context');
 ui('click','#asset-picker');
 const notebook=await evaluate('FIX.nid');
 const option=await evaluate(`Array.from(document.querySelector('[name=asset]').options).find(o=>o.textContent.startsWith('Linked analysis')).value`);
 ui('fill','[name=asset]',option);
 ui('click','.objective-dialog [type=submit]');
 for(let i=0;i<100;i++){if(await evaluate(`!document.querySelector('.objective-dialog')`))break;await new Promise(r=>setTimeout(r,30));}
 assert(await evaluate(`(()=>{const t=termSessions.find(s=>s.name===termCurrentSession),holder=document.createElement('div');holder.innerHTML=_termSessionPillHtml(t,0);return holder.querySelector('.sess-icon .ft-nb')&&LabObjectives.terminalAsset(t).target.resource_id===FIX.nid})()`),'picker replaces GitHub with the notebook and adopts its icon');
 ui('command','terminal-select','--json',JSON.stringify({name:'ui-shell'}));
 ui('click','[data-objective-bucket=objective] [data-objective-resource="'+notebook+'"]');
 assert(await evaluate(`termCurrentSession===${JSON.stringify(launched[0].name)}&&assetOpened.at(-1)===FIX.nid`),'notebook selects its terminal');
 ui('contextmenu','[data-objective-bucket=objective] [data-objective-resource="'+notebook+'"]');
 ui('click',control('Unlink from terminal · First defined'));
 ui('wait','#notice','--text','Asset unlinked.');
 data=cli('api','call','GET','/api/objectives','--query','workspace_id=demo');
 assert(JSON.stringify(data.terminal_links[launched[0].session_id])===original,'unlink restores the original task-only mapping');
 // Make primary uses the real menu and API, retaining each terminal's own asset.
 for(const [row,resource] of [[launched[0],notebook],[launched[1],process.argv[4]]])cli('api','call','POST','/api/objectives','--json',JSON.stringify({workspace_id:'demo',action:{type:'terminal-asset',session_id:row.session_id,objective_id:objective,resource_id:resource}}));
 await evaluate(`LabObjectives.load(undefined,true);window.primarySessionsBefore=JSON.stringify(termSessions)`);
 ui('command','terminal-select','--json',JSON.stringify({name:launched[1].name}));
 ui('click','#terminal-menu');
 assert(await evaluate(`document.querySelector('[data-action=make-primary]')&&!document.querySelector('[data-action=merge-parent]')`),'real terminal menu offers Make primary');
 ui('click',control('Make primary'));
 for(let i=0;i<100;i++){if(await evaluate(`automationGroup.tabParents[${JSON.stringify(launched[0].logical_name)}]===${JSON.stringify(launched[1].logical_name)}`))break;await new Promise(r=>setTimeout(r,30));}
 data=cli('api','call','GET','/api/objectives','--query','workspace_id=demo');
 assert(data.terminal_links[launched[1].session_id].task_id===task&&data.terminal_links[launched[0].session_id].primary===false,'new primary owns the task in persisted metadata');
 assert(data.terminal_links[launched[0].session_id].asset.resource_id===notebook&&data.terminal_links[launched[1].session_id].asset.resource_id===process.argv[4],'promotion preserves both asset bindings');
 assert(await evaluate(`JSON.stringify(termSessions)===primarySessionsBefore&&!automationGroup.tabParents[${JSON.stringify(launched[1].logical_name)}]&&termCurrentSession===${JSON.stringify(launched[1].name)}`),'promotion changes no session identity, launch folder or command and activates its own console');
 assert(await evaluate(`(()=>{const primary=termSessions.find(s=>s.name===termCurrentSession),old=termSessions.find(s=>s.name===${JSON.stringify(launched[0].name)});return LabObjectives.taskForTerminal(primary).primary&&LabObjectives.taskForTerminal(old).primary===false&&_termSessionVisual(primary).icon.includes('github')&&_termSessionVisual(old).icon.includes('ft-nb')})()`),'new primary and previous primary keep their separate icons and task context');
 ui('command','terminal-select','--json',JSON.stringify({name:'ui-shell'}));openTask();
 assert(await evaluate(`termCurrentSession===${JSON.stringify(launched[1].name)}`),'task clicks activate the newly chosen primary');
 // Explicit New → Current task must POST a new session every time.
 const previousNames=await evaluate('termSessions.map(t=>t.name)'),extras=[];
 for(let index=0;index<2;index++){
  ui('click','#new-task-terminal');ui('wait','.term-folder-modal');
  ui('click','[data-folder-choice="0"]');
  for(let i=0;i<100;i++){if(await evaluate(`termSessions.length===${previousNames.length+index+1}`))break;await new Promise(r=>setTimeout(r,30));}
  const extra=await evaluate('termSessions.find(t=>t.name===termCurrentSession)');
  assert(!previousNames.includes(extra.name)&&!extras.some(t=>t.name===extra.name),'each Current task launch creates a distinct terminal');extras.push(extra);
  assert(extra.kind==='terminal','new session retains the requested type');
  assert(await evaluate(`!LabObjectives.terminalParents(termSessions,automationGroup.tabParents)[${JSON.stringify(extra.logical_name)}]&&!LabObjectives.taskForTerminal(termSessions.find(t=>t.name===${JSON.stringify(extra.name)})).inherited`),'new terminal belongs directly to the task without a terminal parent');
 }
 data=cli('api','call','GET','/api/objectives','--query','workspace_id=demo');
 assert(data.terminal_links[launched[1].session_id].task_id===task&&extras.every(t=>data.terminal_links[t.session_id].task_id===task&&data.terminal_links[t.session_id].primary===false),'new terminals preserve the automation primary in the real API');
 openTask();assert(await evaluate(`termCurrentSession===${JSON.stringify(launched[1].name)}`),'opening the task still selects its primary');
 // Reload ownership, promote an independent member, and keep the terminal tree unchanged.
 await evaluate('LabObjectives.load(undefined,true);window.peerLayout=JSON.stringify(automationGroup)');
 ui('command','terminal-select','--json',JSON.stringify({name:extras[0].name}));
 assert(await evaluate(`LabObjectives.taskForTerminal(termSessions.find(t=>t.name===termCurrentSession)).title==='CLI task'`),'saved direct membership opens the task after reloading ownership');
 ui('click','#terminal-menu');ui('click',control('Make primary'));
 for(let i=0;i<100;i++){if(await evaluate(`LabObjectives.taskForTerminal(termSessions.find(t=>t.name===${JSON.stringify(extras[0].name)})).primary`))break;await new Promise(r=>setTimeout(r,30));}
 assert(await evaluate('JSON.stringify(automationGroup)===peerLayout'),'Make primary for an independent task member does not create children');
 openTask();assert(await evaluate(`termCurrentSession===${JSON.stringify(extras[0].name)}`),'task navigation follows the independent primary');
 for(const [choice,view] of [[1,'workflow'],[2,'objective']]){
  const count=await evaluate('termSessions.length');ui('click','#new-task-terminal');ui('wait','.term-folder-modal');ui('click',`[data-folder-choice="${choice}"]`);
  for(let i=0;i<100;i++){if(await evaluate(`termSessions.length===${count+1}`))break;await new Promise(r=>setTimeout(r,30));}
  const extra=await evaluate('termSessions.find(t=>t.name===termCurrentSession)');
  data=cli('api','call','GET','/api/objectives','--query','workspace_id=demo');
  assert(data.terminal_links[extra.session_id].view===view&&!data.terminal_links[extra.session_id].task_id,'new terminal has exactly the selected context');
  assert(await evaluate(`!LabObjectives.terminalParents(termSessions,automationGroup.tabParents)[${JSON.stringify(extra.logical_name)}]`),'workspace and Objective launches remain independent of the active terminal');
 }
 data=cli('api','call','POST','/api/objectives','--json',JSON.stringify({workspace_id:'demo',action:{type:'create',name:'Created through API'}}));
 const added=data.objectives.find(o=>o.name==='Created through API');
 ui('command','objective-select','--json',JSON.stringify({objective:added.id}));
 assert(await evaluate(`LabObjectives.terminalLaunchContext().id===${JSON.stringify(added.id)}`),'UI navigation sees an API-created Objective immediately');
 const opened=cli('workspace','open','demo','--client',view.id);assert(opened.workspace==='demo'&&await evaluate(`document.querySelector('#view-status').textContent===FIX.folder&&new URL(location.href).searchParams.get('workspace')===FIX.folder`),'workspace command awaits real in-page navigation');
 // Closing the automation primary must explicitly confirm and purge all descendants.
 const nested=cli('api','call','POST','/api/term/sessions','--json',JSON.stringify({workspace_id:'demo',kind:'terminal',name:'close-nested'}));
 await evaluate(`termSessions.push(${JSON.stringify(nested)});automationGroup.tabParents[${JSON.stringify(nested.logical_name)}]=${JSON.stringify(launched[0].logical_name)};termCurrentSession=${JSON.stringify(launched[1].name)};
 _termRefreshSessionsForWorkspaceId=async()=>{termSessions=await fetch('/api/term/sessions?workspace_id=demo').then(r=>r.json())};`);
 const groupNames=[launched[0].name,launched[1].name,nested.name];
 ui('click','#terminal-menu');const rejected=ui('click','[data-action=close]');
 assert(rejected.native_dialogs.some(dialog=>JSON.stringify(dialog).includes('All 2 child terminals')),'native confirmation explicitly includes nested children');
 let live=cli('api','call','GET','/api/term/sessions','--query','workspace_id=demo');
 assert(groupNames.every(name=>live.some(row=>row.name===name)),'cancel keeps every group process and tab');
 ui('click','#terminal-menu');ui('click','[data-action=close]','--confirm','yes');
 for(let i=0;i<200;i++){if(await evaluate(`_termCloseTabsPending.size===0`))break;await new Promise(r=>setTimeout(r,30));}
 live=cli('api','call','GET','/api/term/sessions','--query','workspace_id=demo');
 const savedSessions=cli('api','call','GET','/api/term/sessions/saved','--query','workspace_id=demo');
 assert(groupNames.every(name=>!live.some(row=>row.name===name))&&live.some(row=>row.name===extras[0].name),'confirmed close kills the full family and preserves independent task terminals');
 assert([launched[0].logical_name,launched[1].logical_name,nested.logical_name].every(logical=>!savedSessions.some(row=>row.name===logical)),'deleted children stay removed from saved sessions after reload');
 assert(await evaluate(`!Object.keys(automationGroup.tabParents).length`),'closed hierarchy is removed from the browser layout');
 ws.close();console.log('PASS');
})().catch(e=>{console.error(e.stack);process.exit(1)});
'''
    try:
        for _ in range(150):
            if (profile/'DevToolsActivePort').is_file() and server.started: break
            time.sleep(.05)
        import sys
        result=subprocess.run(['node','-e',driver,str(profile),base,sys.executable,rid,tid],capture_output=True,text=True,timeout=90)
        assert result.returncode==0,result.stdout+result.stderr
        assert 'PASS' in result.stdout
        assert term._get_workspace_sessions(monorepo,'demo')[0]['label']=='Review renamed'
    finally:
        process.terminate();process.wait(timeout=10)
        server.should_exit=True;thread.join(timeout=10);listener.close()
