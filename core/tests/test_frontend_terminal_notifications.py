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
 assert(host.getBoundingClientRect().top===96&&Math.abs(innerWidth-host.getBoundingClientRect().right-12)<1,'stack sits at the top right below navigation');
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
