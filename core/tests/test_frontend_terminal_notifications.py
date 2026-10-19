"""Floating report cards: persistence, exact navigation and destination cues."""
from .test_frontend_terminal_ui import ROOT, _run_node, _js_between
from .test_frontend_terminal_completion import CLOCK, MODULE
from .test_frontend_project_cache import _check_project_html

NOTIFICATIONS = (ROOT / 'core/src/core/static/js/lib/terminal-notifications.js').read_text()
DOCUMENTS = (ROOT / 'core/src/core/static/js/lib/workspace-documents.js').read_text()
NAVIGATION = _js_between('  let _termNotificationNavigation =', '  window.LabTerminalNotifications?.configure(').replace('location.href', 'navLocation.href')


def test_notification_lifetime_shared_reports_and_stale_clicks():
    result = _run_node(CLOCK + r'''
document.getElementById=()=>null;
let now=1000000;
Date.now=()=>now;
''' + MODULE + NOTIFICATIONS + r'''
(async()=>{
let C=window.LabTerminalCompletion,N=window.LabTerminalNotifications;
const s={...session('attention'),workspace_id:'demo',vault:'owner',llm_controlled:true};
s.terminal_status.updated_at=now/1000;
N.configure({open:async item=>s});
const snapshot={'owner::demo':[s],'borrower::same-id':[s]};N.update(snapshot);
let item=N.items()[0];
assert(N.items().length===1&&item.owner.vault==='owner','one message for all shared views, original owner');
now+=600000;
assert(N.items().length===1,'attention never expires');
assert(await N.open(item.key,item.report_id),'red opens its terminal');
assert(N.items().length===1&&C.status(s).state==='attention','opening red never clears it');
C.input(s,'yes\r');assert(!N.items().length,'responding immediately replaces attention with yellow');
s.terminal_status={...report('finished',2),updated_at:now/1000};N.update(snapshot);
now+=7*24*60*60*1000;N.render();
assert(N.items().length===1&&C.status(s).state==='finished','green stays after a week without clicks');
N.update(snapshot);assert(N.items().length===1,'polling preserves unreviewed completion');
''' + MODULE + NOTIFICATIONS + r'''
C=window.LabTerminalCompletion;N=window.LabTerminalNotifications;
let highlights=0;
N.configure({open:async()=>s,highlight:()=>{highlights++;assert(!C.status(s),'highlight runs after review and its tab rerender');}});
N.update(snapshot);assert(N.items().length===1,'reloading retains old unreviewed green');
s.terminal_status={...report('finished',3),updated_at:now/1000};N.update(snapshot);item=N.items()[0];
assert(await N.open(item.key,item.report_id),'green opens');
assert(!N.items().length&&!C.status(s),'green click reviews exact report across views');
assert(highlights===1,'successful opening highlights the destination');
s.terminal_status={...report('finished',4),updated_at:now/1000};N.update(snapshot);item=N.items()[0];
let release;N.configure({open:()=>new Promise(resolve=>release=resolve)});
const click=N.open(item.key,item.report_id);
s.terminal_status={...report('finished',5),updated_at:now/1000};N.update(snapshot);release(s);await click;
assert(N.items()[0].report_id==='event-5','slow click cannot consume a newer finish');
N.configure({open:async()=>null});item=N.items()[0];
assert(!await N.open(item.key,item.report_id)&&N.items().length===1,'failed/cancelled navigation preserves message');
N.update({});assert(!N.items().length,'ended sessions leave no orphan messages');
console.log(JSON.stringify({passed:true}));
})();
''')
    assert result['passed']


NAV_SETUP = r'''
let scope={workspace_id:'start',vault:'other'},termSessions=[],termCurrentSession=null,_termTabActivationSeq=0;
const _termRememberLast=()=>{};
const navLocation={href:'https://lab/start'};
let workspacesList=[{name:'demo',vault:'wrong',path:'/wrong/demo'}, {name:'demo',vault:'owner',path:'/owner/demo'}];
const _termActiveWorkspaceId=()=>scope.workspace_id,_termVaultId=()=>scope.vault;
const _termRecentScopeKey=()=>scope.vault+'::'+scope.workspace_id;
const _workspaceVaultId=row=>row.vault;
const calls=[];
const fetchRepos=async()=>workspacesList;
const goToWorkspace=async path=>{calls.push(['workspace',path]);scope={workspace_id:'demo',vault:'owner'};navLocation.href=path;};
const goToProductivity=async()=>{calls.push(['home']);scope={workspace_id:'__self__',vault:null};navLocation.href='/home';};
const goToAssistant=async()=>{calls.push(['assistant']);scope={workspace_id:'__assistant__',vault:'__assistant__'};navLocation.href='/assistant';};
let refresh=async()=>{termSessions=[target];};
const _termRefreshSessionsForWorkspaceId=async()=>{await refresh();return true;};
const _termRememberVisibility=()=>{},_termVisibilityKey=()=>'',termStartPeriodicRefresh=()=>{};
const termToggleCollapse=()=>document.body.classList.remove('term-collapsed');
const _termActivateTab=async(name,options)=>{calls.push(['activate',name,options]);termCurrentSession=name;if(typeof termRenderSessionList==='function')termRenderSessionList();};
window.LabObjectives={load:async()=>{},terminalObjective:()=>({id:'exact-objective'}),
 selectObjective:(id,options)=>calls.push(['objective',id,options]),openForTerminal:()=>true};
'''


def test_notification_navigation_uses_owner_incarnation_and_cancels_late_reads():
    result = _run_node(CLOCK + MODULE + r'''
document.body={classList:{add(){},remove(){},contains:()=>false}};
const target={...session('finished'),workspace_id:'demo',vault:'owner'};
''' + NAV_SETUP + NAVIGATION + r'''
(async()=>{
const item={key:window.LabTerminalCompletion.key(target),owner:{workspace_id:'demo',vault:'owner'}};
assert(await _termOpenNotification(item)===target,'opens exact session');
assert(calls[0][1]==='/owner/demo','same-named workspace in another vault is not selected');
assert(calls[1][0]==='objective'&&calls[1][1]==='exact-objective'&&!calls[1][2].activateTerminal,'selects Objective without starting its main');
assert(calls[2][1]===target.name,'activates requested terminal');
assert(calls[2][2].deferWebgl,'notification arrival renders before graphics setup');
let release;refresh=()=>new Promise(resolve=>release=resolve);
const pending=_termOpenNotification(item);await Promise.resolve();
scope={workspace_id:'elsewhere',vault:'owner'};navLocation.href='/elsewhere';release();
assert(await pending===null&&calls.length===3,'late listing cannot undo newer user navigation');
scope=item.owner;refresh=async()=>{termSessions=[{...target,tmux_id:'$99'}];};
let error;try{await _termOpenNotification(item)}catch(e){error=e.message;}
assert(error?.includes('no longer running'),'same name on a recreated session is never opened');
for(const special of ['__self__','__assistant__']){
 scope={workspace_id:'start',vault:'other'};target.workspace_id=special;target.vault=special==='__self__'?'owner':special;
 refresh=async()=>{termSessions=[target];};
 assert(await _termOpenNotification({key:window.LabTerminalCompletion.key(target),owner:{workspace_id:special,vault:target.vault}})===target,'special scope routes to its exact terminal');
}
console.log(JSON.stringify({passed:true}));
})();
''')
    assert result['passed']


def test_floating_notifications_in_chrome(tmp_path):
    setup = r'''
const assert=(ok,message)=>{if(!ok)throw Error(message)};
const until=async fn=>{for(let i=0;i<100;i++){if(fn())return;await new Promise(resolve=>setTimeout(resolve,5));}throw Error('Timed out '+fn)};
let now=Date.now();Date.now=()=>now;
const report=(state,revision,message)=>({version:1,state,revision,id:'r'+revision,updated_at:now/1000,message});
const target={name:'exact-terminal',logical_name:'codex',workspace_id:'demo',vault:'owner',created:1,tmux_id:'$1',tmux_socket:'owned',llm_controlled:true,terminal_status:report('attention',1,'Please review <preview> & choose a branch')};
const finished={...target,name:'second-terminal',tmux_id:'$2',logical_name:'tests',terminal_status:report('finished',2,'Checks passed')};
const home={...target,name:'home-terminal',tmux_id:'$3',workspace_id:'__self__'};
const assistant={...target,name:'assistant-terminal',tmux_id:'$4',workspace_id:'__assistant__',vault:'__assistant__'};
let snapshot={'owner::demo':[target,finished],'borrower::demo':[target], 'owner::__self__':[home],'__assistant__::__assistant__':[assistant]};
const explorerToast=message=>{throw Error(message)};
window.fetch=async()=>({ok:true,json:async()=>structuredClone(snapshot)});
let groupCollapsed=true;
function termRenderSessionList(){
 const rail=document.getElementById('termSessionList');
 rail.innerHTML='<div style="height:1200px;flex:none"></div><div class="term-tab-group"><button data-tab-group="fixture" aria-expanded="'+!groupCollapsed+'">Group</button><div class="term-tab-group-tabs" '+(groupCollapsed?'hidden':'')+'>'+termSessions.map(s=>'<span class="sess '+(s.name===termCurrentSession?'active':'')+'" data-name="'+s.name+'"><span class="sess-icon">💻</span><span class="sess-label">'+s.logical_name+'</span></span>').join('')+'</div></div>';
 _termPaintNotificationHighlight();
}
const termUpdateTabGroup=()=>{groupCollapsed=false;termRenderSessionList();};
'''
    checks = r'''
(async()=>{try{
 const N=LabTerminalNotifications,C=LabTerminalCompletion,W=LabWorkspaceDocuments;
 N.configure({open:_termOpenNotification,highlight:_termHighlightNotification,label:row=>(row.owner.workspace_id==='__self__'?'Home':row.owner.workspace_id==='__assistant__'?'Assistant':'Client / Demo')+' / '+row.session.logical_name,error:explorerToast});
 await W.poll(true);
 const host=document.getElementById('termNotifications');
 assert(!host.closest('.term-panel')&&getComputedStyle(host).position==='fixed','cards float independently of terminal panel');
 assert(Math.abs(innerHeight-host.getBoundingClientRect().bottom-12)<1&&Math.abs(innerWidth-host.getBoundingClientRect().right-12)<1,'stack sits at the bottom right');
 document.body.classList.add('term-open');
 const consoleHeight=document.querySelector('.term-stage').getBoundingClientRect().height;
 host.hidden=true;
 assert(document.querySelector('.term-stage').getBoundingClientRect().height===consoleHeight,'notifications reserve no console space');
 host.hidden=false;document.body.classList.remove('term-open');
 assert(document.getElementById('termPanel').getClientRects().length===0&&host.getClientRects().length,'notifications survive closing the terminal panel');
 assert(host.children.length===4,'deduplicated messages from every scope');
 assert(host.firstElementChild.classList.contains('attention')&&host.lastElementChild.classList.contains('finished'),'red comes first');
 assert(host.textContent.includes('Please review <preview> & choose a branch')&&!host.querySelector('preview'),'messages are literal text, never HTML');
 assert(document.querySelectorAll('.workspace-attention-needed').length===3,'red wins over green including Home and Assistant');
 const red=host.firstElementChild;red.focus();assert(document.activeElement===red,'message accepts keyboard focus');
 red.click();await until(()=>termCurrentSession===target.name&&!host.querySelector('button:disabled'));
 assert(scope.vault==='owner'&&calls.some(row=>row[0]==='objective'&&row[1]==='exact-objective'),'cross-vault click opens Objective and exact terminal');
 assert(host.children.length===4&&C.status(target).state==='attention','red stays after click');
 let tab=document.querySelector('.term-notification-target'),rail=document.getElementById('termSessionList');
 assert(tab?.dataset.name===target.name&&!groupCollapsed,'red opens its group and highlights the exact tab');
 assert(tab.getAnimations().some(a=>a.animationName==='term-notification-arrival'),'destination has an actual running pulse animation');
 assert(rail.scrollTop>0&&tab.getBoundingClientRect().top>=rail.getBoundingClientRect().top&&tab.getBoundingClientRect().bottom<=rail.getBoundingClientRect().bottom,'offscreen destination scrolls into the rail');
 await new Promise(resolve=>setTimeout(resolve,120));
 const beforePulse=_termNotificationHighlight.started;
 host.firstElementChild.click();await until(()=>_termNotificationHighlight.started>beforePulse);
 assert(document.querySelectorAll('.term-notification-target').length===1,'repeat red click restarts one destination cue');
 C.input(target,'main\r');
 assert(![...host.children].some(row=>row.dataset.key===C.key(target)),'responding removes message instantly');
 assert(document.querySelector('[data-kind=workspace] .workspace-attention-working'),'workspace immediately becomes yellow');
 target.terminal_status=report('working',3,'Implementing');snapshot['owner::demo']=[target,finished];W.updateSessions('owner::demo',[target,finished]);
 refresh=async()=>{termSessions=[target,finished];};
 host.querySelector('.finished').click();await until(()=>termCurrentSession===finished.name&&!C.status(finished));
 assert(!host.querySelector('.finished'),'green message and terminal status clear together');
 tab=document.querySelector('.term-notification-target');
 assert(tab?.dataset.name===finished.name&&tab.getAnimations().length,'green tab pulses after the acknowledgement rebuild');
 const started=_termNotificationHighlight.started;
 await new Promise(resolve=>setTimeout(resolve,80));termRenderSessionList();
 assert(!tab.isConnected&&document.querySelector('.term-notification-target')?.dataset.name===finished.name&&_termNotificationHighlight.started===started,'poll rebuild keeps the cue without restarting its duration');
 finished.terminal_status=report('finished',4,'Another completion');W.updateSessions('owner::demo',[target,finished]);
 assert(host.querySelector('.finished'),'new completion has a new message');
 now+=7*24*60*60*1000;N.render();
 assert(host.querySelector('.finished')&&C.status(finished).state==='finished','green card and status remain after a week');
 const existing=host.firstElementChild;N.render();assert(host.firstElementChild===existing,'unchanged refresh preserves focus and DOM');
 for(const width of [340,400]){host.style.width=width+'px';assert(host.scrollWidth<=width+2,'cards fit narrow and wide layouts');}
 assert(getComputedStyle(host).overflowY==='auto'&&host.clientHeight<=480,'long stacks scroll without consuming the console');
 assert(getComputedStyle(host.querySelector('.attention')).backgroundColor==='rgb(156, 48, 56)','attention has a red card background');
 const firstBox=host.children[0].getBoundingClientRect(),secondBox=host.children[1].getBoundingClientRect();
 assert(document.elementFromPoint(firstBox.x+20,firstBox.y+20).closest('.term-notification')===host.children[0],'card receives pointer clicks');
 assert(!document.elementFromPoint(firstBox.x+20,(firstBox.bottom+secondBox.top)/2).closest('.term-notifications'),'gaps pass clicks to the interface underneath');
 finished.terminal_status=report('finished',5,'Checks passed — ready to review');W.updateSessions('owner::demo',[target,finished]);
 assert(getComputedStyle(host.querySelector('.finished')).backgroundColor==='rgb(28, 104, 72)','finished has a green card background');
 await new Promise(resolve=>setTimeout(resolve,2450));
 assert(!document.querySelector('.term-notification-target')&&!_termNotificationHighlight,'only the brief cue ends automatically');
 assert(host.querySelector('.finished'),'the green notification stays after its tab cue ends');
 document.body.classList.remove('term-open');
 document.body.dataset.result='pass';
}catch(error){document.body.dataset.result='fail';document.body.append(String(error.stack||error));}})();
'''
    css = (ROOT / 'core/src/core/static/css/lab-shell.css').read_text() + (ROOT / 'core/src/core/static/css/workspace-documents.css').read_text()
    template = (ROOT / 'core/src/core/templates/index.html').read_text()
    panel = template.split('<div class="term-panel"', 1)[1].split('<div class="term-group-menu"', 1)[0]
    assert 'id="termNotifications"' not in panel
    html = '<!doctype html><meta charset="utf-8"><style>:root{--red:#f85149;--green:#3fb950;--yellow:#d29922;--bg-secondary:#161b22;--text-primary:#c9d1d9;--border:#30363d;--term-width:400px;}</style><style>'+css+'</style><body><div class="workspace-tab" data-kind="workspace" data-workspace-id="demo" data-vault="owner"><button class="x">×</button></div><div class="workspace-tab" data-kind="productivity"></div><div class="workspace-tab" data-kind="assistant"></div><div class="term-panel"'+panel+'<div id="termNotifications" class="term-notifications"></div><script>'+setup+NAV_SETUP+MODULE+NOTIFICATIONS+DOCUMENTS+NAVIGATION+checks+'</script>'
    _check_project_html(tmp_path, html, focused=True, screenshot=True)


def test_notification_selects_owning_task_and_keeps_assets_accessible_in_chrome(tmp_path):
    objectives = (ROOT / 'core/src/core/static/js/lib/workspace-objectives.js').read_text()
    activation = _js_between('  async function _termActivateTab(', '  function _termHomeAssociationHtml(')
    navigation_setup = NAV_SETUP.replace("const _termActivateTab=async(name,options)=>{calls.push(['activate',name,options]);termCurrentSession=name;if(typeof termRenderSessionList==='function')termRenderSessionList();};", activation)
    tab_click = _js_between("      node.addEventListener('click', (event) => {\n        _termHideSessionTooltip();", "    el.querySelectorAll('[data-divider-options]')").rsplit('\n    });', 1)[0]
    setup = r'''
const assert=(ok,message)=>{if(!ok)throw Error(message)};
const until=async fn=>{for(let i=0;i<100;i++){if(fn())return;await new Promise(r=>setTimeout(r,5));}throw Error('Timed out '+fn)};
const report=(state,id)=>({version:1,state,id,revision:1,updated_at:Date.now()/1000,message:'Review this result'});
const target={name:'secondary',logical_name:'secondary',session_id:'secondary',created:1,tmux_id:'$1',tmux_socket:'owned',workspace_id:'demo',vault:'owner',terminal_status:report('attention','red')};
const primary={...target,name:'primary',logical_name:'primary',session_id:'primary',tmux_id:'$2',terminal_status:null};
const child={...target,name:'child',logical_name:'child',session_id:'child',tmux_id:'$3',terminal_status:report('finished','green')};
const task=(id,title)=>({id,title,children:[],status:'in_progress',done:false,document_id:'details',tab_id:id,assets:[{id:'review',resource_id:'review'}]});
const nested=task('nested','Owning subtask'),parent=task('parent','Parent task');parent.children=[nested];
const objective=(id,tasks)=>({id,name:id,path:'/workspace/'+id,purpose:'',color:'#58a6ff',tasks,resources:[{id:'details',kind:'document',title:'Task details',path:id+'/details.md',content:{tabs:[parent,nested].map(t=>({id:t.id,title:t.title,body:'Task specification'}))}},{id:'review',kind:'document',title:id+' review asset',path:id+'/review.md',content:{body:'Review material'}}],worktrees:[],shared_assets:[],archived_assets:[],trashed_assets:[]});
const fixture={enabled:true,revision:'one',focused:['other','owning'],objectives:[objective('other',[task('nested','Wrong task')]),objective('owning',[parent])],terminal_links:{
 primary:{objective_id:'owning',task_id:'nested'},
 secondary:{objective_id:'owning',task_id:'nested',primary:false,asset:{objective_id:'owning',folder:{root:'/workspace/owning',path:'.'}}}
}};
window.fetch=async()=>({ok:true,json:async()=>structuredClone(fixture)});
window.marked={};window.DOMPurify={};
window.LabMarkdownEditor={create:(node,options)=>{node.textContent=options.body;return {value:options.body,destroy(){},focus(){}}}};
const errors=[],activated=[],created=[],opened=[];let fileRoot='/workspace';
const _termHideSessionTooltip=()=>{},termCloseGroupMenu=()=>{},_termSelectTab=()=>{},explorerToast=message=>errors.push(message);
const termDeadSessions=new Set(),_termIsScopeActive=id=>id===scope.workspace_id,_termCancelPendingLinkedFileOpen=()=>{};
const termAttach=async(name,workspace,options)=>{termCurrentSession=name;calls.push(['attach',name,options]);},_termOpenLinkedFile=()=>{throw Error('Unexpected file fallback')};
window.LabExternalLinks={open:(url,options)=>opened.push(['url',url,options])};
window.addEventListener('error',e=>errors.push(e.message));window.addEventListener('unhandledrejection',e=>errors.push(String(e.reason)));
'''
    checks = r'''
(async()=>{try{
 const O=LabObjectives,N=LabTerminalNotifications,C=LabTerminalCompletion;
 const showFile=(kind,value)=>{opened.push([kind,value]);document.getElementById('content').innerHTML='<article>Native '+kind+' viewer</article>';};
 O.connect({context:()=>({...scope,path:'/workspace'}),scopeRoot:()=>fileRoot,selectWorktree:row=>{fileRoot=row.path},
  openFolder:folder=>opened.push(['folder',folder]),openFile:file=>showFile('file',file),openNotebook:resource=>showFile('notebook',resource),
  refreshTabs:()=>document.getElementById('tabs').innerHTML=O.tabsHtml('/workspace'),prepareCenter:()=>{},
  sessions:()=>termSessions,parentTerminal:s=>s.name==='child'?primary:null,
  activateLinkedTerminal:ids=>activated.push(ids),createTaskTerminal:()=>created.push(true)});
 refresh=async()=>{termSessions=[primary,target,child];};await refresh();
 await O.load();O.selectObjective('owning',{activateTerminal:false});O.openTask('nested');
 O.openForTerminal(target);
 assert(O.terminalLaunchContext().task?.id==='nested','ordinary linked-folder navigation retains its owning task');
 assert(opened.at(-1)?.[0]==='folder','linked folder opens while keeping task assets');
 N.configure({open:_termOpenNotification,label:row=>row.session.logical_name,error:message=>errors.push(message)});
 N.update({'owner::demo':[target,child]});
 const open=async s=>{const button=[...document.querySelectorAll('.term-notification')].find(node=>node.dataset.key===C.key(s));assert(button,'notification exists');button.click();await until(()=>termCurrentSession===s.name&&!document.querySelector('.term-notification:disabled'));assert(calls.filter(row=>row[0]==='attach').at(-1)?.[2].deferWebgl,'notification passes deferred rendering through real tab activation');};
 const checkTask=()=>{
  const context=O.terminalLaunchContext();
  assert(context.id==='owning'&&context.task?.id==='nested','owning Objective and exact nested task are selected');
  assert(document.querySelector('#tabs [data-current-objective]')?.textContent.includes('Owning subtask'),'task is selected in the top navigation');
  assert(document.querySelector('#content [data-task-mode-head]')?.dataset.taskId==='nested','task header stays mounted above the opened asset');
  assert(document.querySelector('[data-objective-bucket="task"]')?.textContent.includes('owning review asset'),'owning task assets stay available');
  assert(!activated.length&&!created.length,'notification never switches to the primary or creates a terminal');
 };
 await open(target);checkTask();
 assert(termCurrentSession==='secondary'&&C.status(target).state==='attention','red selects exact non-primary terminal without clearing attention');
 const asset=document.querySelector('[data-objective-bucket="task"] [data-objective-resource="review"]');
 assert(asset,'task review asset is clickable');asset.click();
 assert(document.getElementById('content').textContent.includes('Review material'),'task asset can actually be opened');
 checkTask();
 fixture.terminal_links.secondary.asset={objective_id:'other',resource_id:'review'};fixture.revision='cross-objective asset';
 await O.load(undefined,true);O.selectObjective('other',{activateTerminal:false});
 await open(target);checkTask();
 assert(document.getElementById('content').textContent.includes('Task specification'),'notification prioritizes owning task over an unrelated linked asset');
 O.selectObjective('other',{activateTerminal:false});await open(child);checkTask();
 assert(termCurrentSession==='child'&&!C.status(child),'green child inherits owning task while keeping its exact terminal and reviewing green');
 await O.load(undefined,true);checkTask();

 // Exercise the real terminal-rail click listener, not just the navigation helper.
 const clickTab=async s=>{mountTab(s);document.querySelector('#terminalRail [data-name]').click();await until(()=>termCurrentSession===s.name);assert(!calls.filter(row=>row[0]==='attach').at(-1)?.[2].deferWebgl,'ordinary tab keeps its renderer policy');};
 const owner=fixture.objectives[1];
 owner.resources.push({id:'analysis',kind:'notebook',title:'Analysis notebook',path:'owning/analysis.ipynb'},
  {id:'notes',kind:'document',title:'Notes',path:'owning/notes.md',content:{tabs:[{id:'result',title:'Results',body:'Exact linked results'},{id:'other',title:'Other',body:'Wrong tab'}]}},
  {id:'links',kind:'link',title:'Issue',url:'https://example.com',sublinks:[{id:'thread',title:'Thread',url:'https://example.com/thread'}]});
 nested.assets.push({resource_id:'analysis'},{resource_id:'notes',tab_id:'result'},{resource_id:'links',sub_link_id:'thread'});
 parent.assets.push({resource_id:'notes'});
 const relink=async asset=>{fixture.terminal_links.secondary={objective_id:'owning',primary:false,asset:{objective_id:'owning',...asset}};fixture.revision+='!';await O.load(undefined,true);O.selectObjective('other',{activateTerminal:false});};
 await relink({resource_id:'analysis'});
 const saved=JSON.stringify(fixture.terminal_links);
 await clickTab(target);checkTask();
 assert(opened.at(-1)?.[0]==='notebook'&&opened.at(-1)[1].id==='analysis','asset-only notebook terminal opens the notebook in its owning task');
 assert(JSON.stringify(fixture.terminal_links)===saved,'navigation never changes stored terminal ownership');
 O.selectObjective('other',{activateTerminal:false});await open(target);checkTask();
 assert(opened.at(-1)?.[0]==='notebook','notification follows the same task and linked notebook navigation');
 await relink({file:{root:'/workspace',path:'/workspace/owning/./analysis.ipynb'}});
 await clickTab(target);checkTask();
 assert(opened.at(-1)?.[0]==='file'&&opened.at(-1)[1].path.endsWith('analysis.ipynb'),'absolute file links resolve the catalog task and open that exact file');
 await relink({resource_id:'notes',tab_id:'result'});await clickTab(target);checkTask();
 assert(document.getElementById('content').textContent.includes('Exact linked results'),'exact document subtab opens inside its task, ahead of the whole-document parent assignment');
 await relink({resource_id:'links',sub_link_id:'thread'});await clickTab(target);checkTask();
 assert(opened.at(-1)?.[0]==='url'&&opened.at(-1)[1]==='https://example.com/thread','exact URL sublink opens while retaining the task');
 fixture.terminal_links.secondary={objective_id:'owning',resource_id:'analysis'};fixture.revision+='legacy';
 await O.load(undefined,true);O.selectObjective('other',{activateTerminal:false});await clickTab(target);checkTask();
 assert(opened.at(-1)?.[0]==='notebook','legacy resource links also select their asset task');
 fixture.terminal_links.child={objective_id:'owning',asset:{objective_id:'owning',resource_id:'notes',tab_id:'result'}};fixture.revision+='child';
 await O.load(undefined,true);O.selectObjective('other',{activateTerminal:false});await clickTab(child);checkTask();
 assert(termCurrentSession==='child'&&document.getElementById('content').textContent.includes('Exact linked results'),'inherited child keeps its exact session and opens its own asset within the task');
 await relink({resource_id:'review'});await clickTab(target);
 assert(!O.terminalLaunchContext().task,'shared assets do not arbitrarily select one of multiple tasks');
 O.openTask('nested');await clickTab(target);checkTask();
 assert(document.getElementById('content').textContent.includes('Review material'),'shared asset retains an already selected matching task');
 await open(target);checkTask();
 assert(document.getElementById('content').textContent.includes('Review material'),'notification retains the selected matching task for a shared asset');
 O.selectObjective('other',{activateTerminal:false});await clickTab(primary);checkTask();
 assert(document.getElementById('content').textContent.includes('Task specification'),'task terminal without an asset opens its task details');
 O.selectObjective('other',{activateTerminal:false});await _termActivateTab(primary.name);checkTask();
 assert(termCurrentSession==='primary','direct terminal activation also selects the task');
 assert(!errors.length,errors.join('\n'));
 document.body.dataset.result='pass';
}catch(error){document.body.dataset.result='fail';document.body.append(String(error.stack||error));}})();
'''
    css = (ROOT / 'core/src/core/static/css/lab-shell.css').read_text() + (ROOT / 'core/src/core/static/css/workspace-objectives.css').read_text()
    tabs = "function mountTab(s){const host=document.getElementById('terminalRail');host.innerHTML='<button data-name=\"'+s.name+'\">'+s.name+'</button>';const node=host.firstElementChild,completionDot=null;"+tab_click+"}"
    html = '<!doctype html><meta charset="utf-8"><style>'+css+'</style><body><div id="tabs" class="repo-tabs"></div><aside id="sidebar"><section data-objectives-sidebar></section></aside><main id="content"></main><div id="terminalRail"></div><div id="termNotifications" class="term-notifications"></div><script>'+setup+navigation_setup+objectives+MODULE+NOTIFICATIONS+NAVIGATION+tabs+checks+'</script>'
    _check_project_html(tmp_path, html, focused=True)


def test_notification_history_survives_working_review_reload_and_stale_clicks():
    result = _run_node(CLOCK + r'''
document.getElementById=()=>null;
''' + MODULE + NOTIFICATIONS + r'''
(async()=>{
let C=window.LabTerminalCompletion,N=window.LabTerminalNotifications;
const s={...session('finished'),workspace_id:'demo',vault:'owner',llm_controlled:true};
const snapshot={'owner::demo':[s],'borrower::demo':[s]};
N.update(snapshot);const key=C.key(s);
assert(C.acknowledge('',s),'review current finish');
assert(!N.items().length&&N.items({history:true}).length===1,'reviewed finish is available in history once');
s.terminal_status=report('working',2);N.update(snapshot);
assert(!N.items().length&&N.items({history:true})[0].report_id==='event-1','working retains previous alert');
''' + MODULE + NOTIFICATIONS + r'''
C=window.LabTerminalCompletion;N=window.LabTerminalNotifications;
N.update(snapshot);
assert(N.items({history:true})[0].report_id==='event-1','retained alert survives reload during working');
N.configure({open:async()=>s});
assert(await N.open(key,'event-1')&&C.status(s).state==='working','opening historical finish never changes working');
for(let i=3;i<=12;i++){s.terminal_status=report(i===12?'attention':'finished',i);N.update(snapshot);}
assert(N.items({history:true}).length===1&&N.items({history:true})[0].report_id==='event-12','ten alerts leave only the latest per terminal');
assert(!await N.open(key,'event-11'),'an obsolete history click is rejected');
C.input({...s,llm_controlled:true},'yes\r');
assert(!N.items().length&&N.items({history:true})[0].report_id==='event-12','submitted response hides red but retains it in history');
s.terminal_status=report('finished',13);N.update(snapshot);
let release;N.configure({open:()=>new Promise(resolve=>release=resolve)});
const pending=N.open(key,'event-13');
s.terminal_status=report('finished',14);N.update(snapshot);release(s);await pending;
assert(C.status(s).state==='finished'&&N.items()[0].report_id==='event-14','historical navigation cannot acknowledge a newer finish');
const newest={...s,name:'newest',tmux_id:'$2',terminal_status:{...report('finished',1),updated_at:1000}};
N.update({'owner::demo':[s,newest]});
assert(N.items({history:true})[0].session.name==='newest','history sorts by creation time across independent terminal revisions');
N.update({'owner::demo':[{...s,tmux_id:'$99',terminal_status:null}]});
assert(!N.items({history:true}).length,'history cannot leak into a recreated terminal with the same name');
const unseen={...s,name:'offline',tmux_id:'$3',terminal_status:report('working',20),terminal_notification:report('finished',19,'Emitted while browser closed')};
N.update({'owner::demo':[unseen]});
assert(!N.items().length&&N.items({history:true})[0].report_id==='event-19','history recovers session alerts this browser never observed');
N.configure({open:async item=>item.session});
assert(await N.open(C.key(unseen),'event-19')&&C.status(unseen).state==='working','unseen historical finish does not change current status');
console.log(JSON.stringify({passed:true}));
})();
''')
    assert result['passed']


def test_notification_center_pagination_dismissal_and_review_in_chrome(tmp_path):
    import json
    import base64
    from core.link_services import SERVICES

    icon_renderer = _js_between('  function _termNotificationIcon(', '  window.LabTerminalNotifications?.configure(')
    static = ROOT / 'core/src/core/static'
    dependencies = (static / 'js/lib/scope-links.js').read_text() + (static / 'js/lib/terminal-automations.js').read_text()
    setup = r'''
const assert=(ok,message)=>{if(!ok)throw Error(message)};
const until=async fn=>{for(let i=0;i<100;i++){if(fn())return;await new Promise(r=>setTimeout(r,5));}throw Error('Timed out '+fn)};
let activeWorkspace='unrelated',activeVault='other-vault',termSessions=[];
const _termActiveWorkspaceId=()=>activeWorkspace,_termVaultId=()=>activeVault;
const _termSubtabParents=()=>({}),_termReadGroupState=()=>({});
const termSessEsc=value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fileIconHtml=path=>'<svg class="ft-icon" width="20" height="20" viewBox="0 0 20 20" data-file-icon="'+termSessEsc(path)+'"><rect x="4" y="2" width="12" height="16" fill="none" stroke="currentColor"/></svg>';
const png='data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aX1cAAAAASUVORK5CYII=';
const icons=[{emoji:'🔬'},{service:'github'},{automation:{builtin:'terminal'}},{automation:{image:png}},{file:'report.ipynb'},{link:{kind:'external',url:'https://github.com/org/repo'}}];
const sessions=Array.from({length:45},(_,i)=>({name:'terminal-'+i,created:1,tmux_socket:'owned',tmux_id:'$'+i,
 workspace_id:'demo',vault:'owner',llm_controlled:true,
 notification_context:{workspace:'Workspace <Alpha>',objective:'Objective & Beta',icon:icons[i%icons.length]},
 terminal_status:{version:1,state:i%2?'attention':'finished',revision:1,id:'r'+i,updated_at:1000+i,message:'Result '+i+' <literal>'+(i===44?' café':'')}}));
let opened=[],fail=false,hold=false,release;
'''
    checks = r'''
(async()=>{try{
 const N=LabTerminalNotifications,C=LabTerminalCompletion;
 const snapshot={'owner::demo':sessions,'borrower::demo':sessions};
 const host=document.getElementById('termNotifications'),outside=document.getElementById('outside');
 document.getElementById('repoTabs').innerHTML='<button class="repo-tab lid-awake-toggle">Lid Awake</button>'+N.buttonHtml();
 const toggle=document.querySelector('[data-terminal-notification-center]');
 const cards=()=>[...host.querySelectorAll('.term-notification')];
 N.configure({icon:_termNotificationIcon,open:async item=>{if(fail)return null;if(hold)await new Promise(resolve=>release=resolve);opened.push(item.session.name);return item.session;}});
 N.update(snapshot);
 for(const s of sessions)if(s.terminal_status.state==='finished')C.acknowledge('',s);
 sessions[42].terminal_status={...sessions[42].terminal_status,state:'working',id:'working',revision:2};N.update(snapshot);
 assert(cards().length===22,'automatic stack has only current attention requests');
 assert(toggle.textContent.trim()==='🔔'&&toggle.querySelector('.keep-alive-switch'),'control shows only a bell and switch, without text');
 assert(toggle.getAttribute('role')==='switch'&&toggle.getAttribute('aria-checked')==='false'&&toggle.getAttribute('aria-label'),'switch has an accessible name and state');
 assert(cards().every(card=>card.classList.contains('active-alert')),'active automatic alerts have the vertical marker');
 toggle.click();
 assert(toggle.getAttribute('aria-expanded')==='true'&&host.classList.contains('history-open'),'button opens the history view');
 assert(toggle.getAttribute('aria-checked')==='true'&&getComputedStyle(toggle.querySelector('.keep-alive-switch'),'::after').transform!=='none','bell switch turns on visually');
 assert(cards().length===20&&cards()[0].textContent.includes('Result 44'),'history starts with newest 20 regardless of red/green');
 assert(cards()[2].textContent.includes('Result 42')&&cards()[2].textContent.includes('History'),'working terminal retains its last notification');

 const search=host.querySelector('[data-notification-search]');
 assert(search?.type==='search'&&search.getAttribute('aria-label')&&document.activeElement===search,'opening focuses an accessible search field');
 assert(Math.abs(innerHeight-host.getBoundingClientRect().bottom-12)<1,'notification center is bottom anchored');
 const find=value=>{const input=host.querySelector('[data-notification-search]');input.value=value;input.dispatchEvent(new Event('input',{bubbles:true}));};
 find('terminal-2');assert(cards().length===11&&cards().some(card=>card.textContent.includes('Result 2')),'search includes older notifications beyond the first page');
 find('WORKSPACE alpha terminal-4');assert(cards().length===6,'multiple case-insensitive keywords match workspace and terminal');
 find('finished result 43');assert(cards().length===0&&host.textContent.includes('No matching notifications.')&&!host.querySelector('[data-notification-more]'),'all keywords must match and empty results are clear');
 find('<literal>');assert(cards().length===20&&host.querySelector('[data-notification-more]')&&!host.querySelector('literal'),'literal markup searches are safe and filtering precedes pagination');
 host.querySelector('[data-notification-more]').click();assert(cards().length===40,'filtered results paginate');
 find('terminal-44');search.focus();search.setSelectionRange(4,4);N.update(snapshot);
 assert(host.querySelector('[data-notification-search]')===search&&document.activeElement===search&&search.selectionStart===4&&cards().length===1,'polling preserves input identity, caret and filtered results');
 find('CAFE');assert(cards().length===1,'message search ignores diacritics');
 search.dispatchEvent(new CompositionEvent('compositionstart',{data:'re'}));find('Result');
 search.dispatchEvent(new CompositionEvent('compositionend',{data:'Result'}));
 assert(host.querySelector('[data-notification-search]')===search&&document.activeElement===search,'composition does not replace the input');
 host.querySelector('[data-notification-clear]').click();
 assert(search.value===''&&cards().length===20&&document.activeElement===search,'clear resets pagination and restores search focus');
 host.scrollTop=host.scrollHeight;
 await new Promise(requestAnimationFrame);
 assert(search.getBoundingClientRect().top>=host.getBoundingClientRect().top&&search.getBoundingClientRect().bottom<=host.getBoundingClientRect().bottom,'search stays visible while scrolling history');
 host.scrollTop=0;

 assert(!cards()[0].classList.contains('active-alert')&&cards()[1].classList.contains('active-alert'),'history and active requests are visibly distinct');
 assert(getComputedStyle(cards()[1],'::before').width==='3px'&&getComputedStyle(cards()[1],'::before').backgroundColor==='rgb(255, 255, 255)','active requests have an actual visible vertical line');
 assert(cards()[0].querySelector('.term-notification-context').textContent.startsWith('Workspace <Alpha> / Objective & Beta / terminal-44')&&!host.querySelector('alpha'),'workspace and Objective precede terminal and status as escaped text');
 assert(cards().every(card=>card.querySelector('.term-notification-terminal-icon')?.nextElementSibling.classList.contains('term-notification-context')),'terminal icon precedes workspace and Objective on every card');
 assert(host.querySelector('.term-notification-terminal-icon [data-link-service="github"]')&&host.querySelector('.term-notification-terminal-icon svg.term-automation-icon')&&host.querySelector('.term-notification-terminal-icon img')&&host.querySelector('[data-file-icon="report.ipynb"]'),'native service, outline, PNG and file icon renderers work from another workspace');
 assert(cards()[0].querySelector('.term-notification-icon').textContent==='✓','terminal icon keeps the separate status symbol');
 sessions[44].notification_context.icon={emoji:'<img src=x onerror=alert(1)>'};N.update(snapshot);
 assert(cards()[0].querySelector('.term-notification-terminal-icon').textContent.includes('<img')&&!cards()[0].querySelector('img'),'custom emoji markup is escaped');
 sessions[44].notification_context.icon=icons[2];N.update(snapshot);
 const originalContext=sessions[44].notification_context;delete sessions[44].notification_context;
 activeWorkspace='demo';activeVault='owner';termSessions=[sessions[44]];
 window.LabObjectives={taskForTerminal:()=>({assetIcon:'🔭'})};N.update(snapshot);
 assert(cards()[0].querySelector('.term-notification-terminal-icon').textContent==='🔭','local session refresh retains the current task icon without the attention descriptor');
 activeWorkspace='unrelated';activeVault='other-vault';N.update(snapshot);
 assert(cards()[0].querySelector('.term-notification-terminal-icon').textContent==='💻','fallback cannot borrow the selected workspace task icon');
 sessions[44].notification_context=originalContext;N.update(snapshot);
 assert(cards().every(card=>card.querySelector('time'))&&!host.querySelector('literal'),'creation dates and escaped messages are visible');
 assert(host.querySelector('[data-notification-more]'),'older notifications can be loaded');
 const same=cards()[0];N.update(snapshot);assert(cards()[0]===same,'unchanged poll retains DOM and pagination');
 host.querySelector('[data-notification-more]').click();
 assert(cards().length===40&&document.activeElement===cards()[20],'load more reveals the next 20 with accessible focus');
 N.update(snapshot);assert(cards().length===40,'polling preserves expanded page');
 host.querySelector('[data-notification-more]').click();
 assert(cards().length===45&&!host.querySelector('[data-notification-more]'),'last page has all unique terminals and no extra load control');
 const redBefore=C.status(sessions[43]);
 outside.click();
 assert(!host.classList.contains('history-open')&&toggle.getAttribute('aria-expanded')==='false','outside click closes history');
 assert(cards().length===22&&C.status(sessions[43]).state===redBefore.state,'outside dismissal preserves actual requests');
 toggle.click();assert(cards().length===20,'reopening resets to the first 20');
 document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true,cancelable:true}));
 assert(!host.classList.contains('history-open')&&document.activeElement===toggle,'Escape closes and returns focus');
 toggle.click();host.querySelector('[data-notification-close]').click();
 assert(!host.classList.contains('history-open'),'close control returns to attention stack');
 toggle.click();fail=true;cards()[0].click();await new Promise(r=>setTimeout(r,0));
 assert(host.classList.contains('history-open'),'failed navigation keeps history open');fail=false;
 cards()[0].click();await until(()=>!host.querySelector('.term-notification:disabled'));
 assert(host.classList.contains('history-open')&&toggle.getAttribute('aria-checked')==='true','successful notification click keeps show-all open');
 assert(opened.at(-1)==='terminal-44'&&!C.status(sessions[44]),'reviewed history activates its terminal');
 cards()[1].click();await until(()=>!host.querySelector('.term-notification:disabled'));
 assert(host.classList.contains('history-open')&&opened.at(-1)==='terminal-43'&&C.status(sessions[43]).state==='attention','another card can be checked without closing show-all or clearing red');
 sessions[44].terminal_status={...sessions[44].terminal_status,id:'new-finish',revision:2,updated_at:2000};N.update(snapshot);
 assert(host.classList.contains('history-open')&&cards()[0].dataset.reportId==='new-finish'&&cards()[0].classList.contains('active-alert'),'new report updates the active marker without closing show-all');
 outside.click();assert(cards().length===23&&cards().some(card=>card.dataset.reportId==='new-finish'),'unreviewed finish returns after outside dismissal');
 toggle.click();find('terminal-44');
 const reviewSearch=host.querySelector('[data-notification-search]');reviewSearch.focus();reviewSearch.setSelectionRange(5,5);
 cards()[0].click();await until(()=>!host.querySelector('.term-notification:disabled'));
 assert(host.classList.contains('history-open')&&!C.status(sessions[44])&&cards()[0].dataset.reportId==='new-finish'&&!cards()[0].classList.contains('active-alert'),'review turns off the marker while the card and list remain');
 assert(host.querySelector('[data-notification-search]')===reviewSearch&&reviewSearch.value==='terminal-44'&&reviewSearch.selectionStart===5&&cards().length===1,'review preserves search, its field and caret');
 find('');
 C.input(sessions[43],'yes\r');
 assert(host.classList.contains('history-open')&&!cards().find(card=>card.dataset.key===C.key(sessions[43])).classList.contains('active-alert'),'responding updates the active marker while keeping show-all open');
 find('terminal-1');assert(cards().length===11,'filter remains available after navigation and review updates');
 outside.click();assert(!host.querySelector('[data-notification-search]')&&cards().length===21,'closing search restores unfiltered live alerts');
 toggle.click();assert(host.querySelector('[data-notification-search]').value===''&&cards().length===20,'reopening starts with an empty search');
 N.update({});assert(!host.hidden&&host.textContent.includes('No notifications yet.'),'empty history is available');outside.click();assert(host.hidden,'empty automatic stack hides');
 N.update(snapshot);toggle.click();
 for(const width of [280,340,400]){host.style.width=width+'px';assert(host.scrollWidth<=width+2,'history fits narrow and wide layouts');
  for(const card of cards()){
   const icon=card.querySelector('.term-notification-terminal-icon'),context=card.querySelector('.term-notification-context');
   assert(icon.getBoundingClientRect().width===16&&context.getBoundingClientRect().left>=icon.getBoundingClientRect().right,'wrapped headers retain a fixed icon before the text');
   for(const child of icon.querySelectorAll('svg,img,.scope-link-icon'))assert(child.getBoundingClientRect().width===16&&child.getBoundingClientRect().height===16,'all icon types fit the header');
  }
 }
 assert(getComputedStyle(host).overflowY==='auto'&&host.clientHeight<=480,'history scrolls in a bounded overlay');
 hold=true;cards()[0].click();outside.click();release();
 await until(()=>!host.querySelector('.term-notification:disabled'));
 assert(!host.classList.contains('history-open')&&toggle.getAttribute('aria-checked')==='false','late navigation never reopens a list dismissed elsewhere');
 toggle.click();
 document.body.dataset.result='pass';
}catch(error){document.body.dataset.result='fail';document.body.append(String(error.stack||error));}})();
'''
    github = base64.b64encode((static / 'img/link-icons/github.svg').read_bytes()).decode()
    css = (static / 'css/lab-shell.css').read_text().replace('url("../img/link-icons/github.svg")', 'url("data:image/svg+xml;base64,' + github + '")')
    html = '<!doctype html><meta charset="utf-8"><style>:root{--bg-primary:#0d1117;--bg-secondary:#161b22;--bg-tertiary:#21262d;--border:#30363d;--text-primary:#c9d1d9;--text-secondary:#8b949e;--accent:#58a6ff;}</style><style>'+css+'</style><body><nav id="repoTabs" class="repo-tabs"></nav><button id="outside" style="position:absolute;top:120px;left:20px">Outside</button><div id="termNotifications" class="term-notifications" role="region" aria-label="Terminal notifications"></div><script>window.LAB_LINK_SERVICES='+json.dumps(SERVICES)+';'+setup+dependencies+icon_renderer+MODULE+NOTIFICATIONS+checks+'</script>'
    _check_project_html(tmp_path, html, focused=True, screenshot=True)


def test_notification_labels_put_native_workspace_and_objective_before_terminal_and_vault():
    label = _js_between('    label:({session, owner}) => {', '  window.LabWorkspaceDocuments?.configure(').split('\n  });', 1)[0]
    result = _run_node(r'''
const assert=(ok,message)=>{if(!ok)throw Error(message)};
const workspaceTabsAll=[{name:'same-id',vault:'wrong',display_name:'Wrong workspace'},
 {name:'same-id',vault:'owner',display_name:'Renamed workspace'}];
const _workspaceVaultId=row=>row.vault,_workspaceDisplayName=row=>row.display_name;
const _vaultById=()=>({name:'Vault name'});
const bridge={''' + label + r'''};
const session={name:'exact',label:'Agent terminal',notification_context:{workspace:'Owner workspace',objective:'Owner Objective'}};
const owner={workspace_id:'same-id',vault:'owner'};
assert(bridge.label({session,owner})==='Owner workspace / Owner Objective / Agent terminal · Vault name','native workspace and Objective come first even for an inactive view');
assert(bridge.label({session:{name:'exact'},owner})==='Renamed workspace / exact · Vault name','fallback uses the exact owner vault');
assert(bridge.label({session:{name:'exact'},owner:{workspace_id:'__self__',vault:'owner'}})==='Home / exact','Home keeps its own context');
console.log(JSON.stringify({passed:true}));
''')
    assert result['passed']


def test_notification_ui_commands_share_history_and_exact_report_navigation():
    commands = _js_between("      'terminal-notifications':", "      'workspace-open':")
    result = _run_node(CLOCK + r'''
document.getElementById=()=>null;
''' + MODULE + NOTIFICATIONS + 'const commands={'+commands+'};' + r'''
(async()=>{
const N=window.LabTerminalNotifications,C=window.LabTerminalCompletion;
const s={...session('finished'),workspace_id:'demo',vault:'owner'};
let polls=0,opened=0;
window.LabWorkspaceDocuments={poll:async()=>{polls++;N.update({'owner::demo':[s]});}};
N.configure({open:async item=>{assert(item.session===s,'command uses exact item');opened++;return s;}});
let rows=await commands['terminal-notifications']();
assert(rows.length===1&&polls===1,'default CLI list refreshes active messages');
C.acknowledge('',s);
assert(!(await commands['terminal-notifications']()).length,'reviewed messages are absent from default CLI list');
rows=await commands['terminal-notifications']({history:true});
assert(rows.length===1&&!rows[0].active,'CLI history includes reviewed messages');
assert(commands['terminal-notification-center']().open,'CLI can open center');
assert(!commands['terminal-notification-center']({open:false}).open,'CLI can close center');
assert((await commands['terminal-notification-open']({key:rows[0].key,report_id:rows[0].report_id})).opened&&opened===1,'CLI can reopen reviewed history');
s.terminal_status=report('finished',2);N.update({'owner::demo':[s]});
assert(!(await commands['terminal-notification-open']({name:s.name,report_id:rows[0].report_id})).opened&&C.status(s),'stale CLI history does not review the new report');
console.log(JSON.stringify({passed:true}));
})();
''')
    assert result['passed']
