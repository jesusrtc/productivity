"""Floating report cards: exact ownership, expiry and click review."""
from .test_frontend_terminal_ui import ROOT, _run_node, _js_between
from .test_frontend_terminal_completion import CLOCK, MODULE
from .test_frontend_project_cache import _check_project_html

NOTIFICATIONS = (ROOT / 'core/src/core/static/js/lib/terminal-notifications.js').read_text()
DOCUMENTS = (ROOT / 'core/src/core/static/js/lib/workspace-documents.js').read_text()
NAVIGATION = _js_between('  let _termNotificationNavigation =', '  window.LabTerminalNotifications?.configure(').replace('location.href', 'navLocation.href')


def test_notification_lifetime_shared_reports_and_stale_clicks():
    result = _run_node(CLOCK + r'''
document.getElementById=()=>null;
let now=1000000, timer;
Date.now=()=>now;
const setTimeout=(fn,ms)=>{timer={fn,ms};return 1;},clearTimeout=()=>{};
''' + MODULE + NOTIFICATIONS + r'''
(async()=>{
const C=window.LabTerminalCompletion,N=window.LabTerminalNotifications;
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
assert(timer.ms===300000,'expiry is scheduled even with no polls');
now+=299999;assert(N.items().length===1,'visible until five minutes');
now++;timer.fn();assert(!N.items().length&&C.status(s).state==='finished','expiry hides message only, green remains');
N.update(snapshot);assert(!N.items().length,'polling does not restart expiry');
s.terminal_status={...report('finished',3),updated_at:now/1000};N.update(snapshot);item=N.items()[0];
assert(await N.open(item.key,item.report_id),'green opens');
assert(!N.items().length&&!C.status(s),'green click reviews exact report across views');
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
const _termActivateTab=async(name,options)=>{calls.push(['activate',name,options]);termCurrentSession=name;};
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
'''
    checks = r'''
(async()=>{try{
 const N=LabTerminalNotifications,C=LabTerminalCompletion,W=LabWorkspaceDocuments;
 N.configure({open:_termOpenNotification,label:row=>(row.owner.workspace_id==='__self__'?'Home':row.owner.workspace_id==='__assistant__'?'Assistant':'Client / Demo')+' / '+row.session.logical_name,error:explorerToast});
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
 C.input(target,'main\r');
 assert(![...host.children].some(row=>row.dataset.key===C.key(target)),'responding removes message instantly');
 assert(document.querySelector('[data-kind=workspace] .workspace-attention-working'),'workspace immediately becomes yellow');
 target.terminal_status=report('working',3,'Implementing');snapshot['owner::demo']=[target,finished];W.updateSessions('owner::demo',[target,finished]);
 refresh=async()=>{termSessions=[target,finished];};
 host.querySelector('.finished').click();await until(()=>termCurrentSession===finished.name&&!C.status(finished));
 assert(!host.querySelector('.finished'),'green message and terminal status clear together');
 finished.terminal_status=report('finished',4,'Another completion');W.updateSessions('owner::demo',[target,finished]);
 assert(host.querySelector('.finished'),'new completion has a new message');
 now+=300000;N.render();
 assert(!host.querySelector('.finished')&&C.status(finished).state==='finished','five minute expiry leaves terminal green');
 const existing=host.firstElementChild;N.render();assert(host.firstElementChild===existing,'unchanged refresh preserves focus and DOM');
 for(const width of [340,400]){host.style.width=width+'px';assert(host.scrollWidth<=width+2,'cards fit narrow and wide layouts');}
 assert(getComputedStyle(host).overflowY==='auto'&&host.clientHeight<=480,'long stacks scroll without consuming the console');
 assert(getComputedStyle(host.querySelector('.attention')).backgroundColor==='rgb(156, 48, 56)','attention has a red card background');
 const firstBox=host.children[0].getBoundingClientRect(),secondBox=host.children[1].getBoundingClientRect();
 assert(document.elementFromPoint(firstBox.x+20,firstBox.y+20).closest('.term-notification')===host.children[0],'card receives pointer clicks');
 assert(!document.elementFromPoint(firstBox.x+20,(firstBox.bottom+secondBox.top)/2).closest('.term-notifications'),'gaps pass clicks to the interface underneath');
 finished.terminal_status=report('finished',5,'Checks passed — ready to review');W.updateSessions('owner::demo',[target,finished]);
 assert(getComputedStyle(host.querySelector('.finished')).backgroundColor==='rgb(28, 104, 72)','finished has a green card background');
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
