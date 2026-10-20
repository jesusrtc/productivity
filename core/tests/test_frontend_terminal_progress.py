from .test_frontend_terminal_ui import ROOT, _run_node
from .test_frontend_project_cache import _check_project_html
from .test_frontend_terminal_completion import MODULE, CLOCK
from .test_frontend_terminal_notifications import NOTIFICATIONS


def test_progress_alert_click_history_resolution_and_hover_in_chrome(tmp_path):
    setup = r'''
const assert=(ok,message)=>{if(!ok)throw Error(message)};
let now=2000000;Date.now=()=>now;
const session={name:'copilot',logical_name:'Copilot',tmux_socket:'owned',tmux_id:'$1',created:1,
 workspace_id:'science',vault:'owner',llm_controlled:true,
 notification_context:{workspace:'Science',objective:'Validate migration'},
 terminal_status:{version:1,state:'working',id:'working',revision:10,updated_at:100,message:'Checking permissions'},
 terminal_progress:{since:100,message:'Checking permissions',alert:{version:1,state:'attention',kind:'stale',
 source:'working',id:'overdue',revision:20,updated_at:1900,message:'WIP overdue',active:true}}};
const snapshot={'owner::science':[session]};
'''
    checks = r'''
(async()=>{try{
 const N=LabTerminalNotifications,C=LabTerminalCompletion,host=document.getElementById('termNotifications');
 let opened=0;N.configure({open:async item=>{opened++;assert(item.session===session,'exact destination');return session;}});
 document.getElementById('toolbar').innerHTML=N.buttonHtml();N.update(snapshot);
 const toggle=document.querySelector('[data-terminal-notification-center]');
 assert(C.status(session).state==='working'&&C.status(session).label.includes('31 min'),'WIP dot and overdue hover');
 assert(host.textContent.includes('Science / Validate migration / Copilot'),'owner context leads');
 assert(host.textContent.includes('31 min')&&host.textContent.includes('Checking permissions'),'age and actual report');
 assert(host.querySelector('.active-alert'),'active marker');
 assert(Math.abs(host.getBoundingClientRect().top-96)<1,'floating progress alert is at the top');
 for(const width of [280,340,400]){host.style.width=width+'px';assert(host.scrollWidth<=width+2,'progress controls fit narrow layouts');}
 const snooze=host.querySelector('[data-notification-snooze]'),box=snooze.getBoundingClientRect();
 assert(document.elementFromPoint(box.x+box.width/2,box.y+box.height/2)===snooze&&!host.querySelector('.term-notification button'),'controls receive real pointer clicks without nested buttons');
 const before=JSON.stringify(session.terminal_status);
 host.querySelector('[data-notification-snooze]').click();
 assert(host.hidden&&!N.items().length&&opened===0,'snooze hides the floating reminder without navigating');
 assert(JSON.stringify(session.terminal_status)===before&&C.status(session).state==='working','snooze never changes the agent report');
 toggle.click();assert(host.textContent.includes('Snoozed until')&&!host.querySelector('.active-alert'),'snoozed reminder stays in searchable history');
 document.getElementById('outside').click();now+=30*60*1000;N.render();
 assert(!host.hidden&&host.querySelector('[data-notification-dismiss]'),'reminder returns after 30 minutes');
 toggle.click();const row=N.items()[0];await N.open(row.key,row.report_id);
 assert(opened===1&&toggle.getAttribute('aria-checked')==='true'&&N.items().length===1,'click keeps alert and show-all');
 host.querySelector('[data-notification-dismiss]').focus();host.querySelector('[data-notification-dismiss]').click();
 assert(!N.items().length&&host.textContent.includes('Dismissed')&&!host.querySelector('.active-alert'),'dismiss hides this reminder but keeps its history');
 assert(document.activeElement===host.querySelector('[data-notification-search]')&&opened===1,'dismiss keeps keyboard focus without opening the terminal');
 assert(JSON.stringify(session.terminal_status)===before&&C.status(session).state==='working','dismiss never reports completion');
 session.terminal_status={...session.terminal_status,id:'new-work',revision:30,updated_at:2000,message:'Permissions checked; running tests'};
 // Even an outdated server progress flag cannot override a newer report.
 N.update(snapshot);
 assert(!N.items().length&&C.status(session).state==='working','fresh report resolves without turning green');
 assert(N.items({history:true})[0].report_id==='overdue'&&!host.querySelector('.active-alert'),'history stays, marker clears');
 assert(host.textContent.includes('History')&&toggle.getAttribute('aria-checked')==='true','refresh keeps history open');
 document.getElementById('outside').click();assert(host.hidden&&toggle.getAttribute('aria-checked')==='false','outside restores current alerts');
 session.terminal_status={...session.terminal_status,id:'done',revision:40,state:'finished',updated_at:2001,message:'Checks passed'};
 session.terminal_progress.alert.active=false;N.update(snapshot);
 assert(N.items()[0].state==='finished','normal explicit completion still works');
 toggle.click();const finished=N.items()[0];await N.open(finished.key,finished.report_id);
 assert(!C.status(session)&&!N.items().length&&toggle.getAttribute('aria-checked')==='true','green review retains the bell');
 // Leave the overdue state visible for screenshot inspection.
 session.tmux_id='$2';session.terminal_status={...session.terminal_status,state:'working',id:'working',revision:50,updated_at:100,message:'Checking permissions'};
 session.terminal_progress.alert.active=true;N.update(snapshot);document.getElementById('outside').click();
 document.body.dataset.result='pass';
}catch(error){document.body.dataset.result='fail';document.body.append(String(error.stack||error));}})();
'''
    css = (ROOT / 'core/src/core/static/css/lab-shell.css').read_text()
    html = '<!doctype html><meta charset="utf-8"><style>:root{--bg-primary:#0d1117;--bg-secondary:#161b22;--bg-tertiary:#21262d;--border:#30363d;--text-primary:#c9d1d9;--text-secondary:#8b949e;--accent:#58a6ff;}body{background:#0d1117;color:#c9d1d9}</style><style>' + css + '</style><body><nav id="toolbar"></nav><button id="outside">Outside</button><div id="termNotifications" class="term-notifications"></div><script>' + setup + MODULE + NOTIFICATIONS + checks + '</script>'
    _check_project_html(tmp_path, html, focused=True, screenshot=True)


def test_progress_mutes_survive_reload_expire_and_protect_new_reports():
    result = _run_node(CLOCK + r'''
document.getElementById=()=>null;
let now=2000000,wake,delay;
Date.now=()=>now;
globalThis.setTimeout=(fn,ms)=>{wake=fn;delay=ms;return 1};
globalThis.clearTimeout=()=>{};
''' + MODULE + NOTIFICATIONS + r'''
let N=window.LabTerminalNotifications;const C=window.LabTerminalCompletion;
const s={...session('working'),workspace_id:'demo',vault:'owner',llm_controlled:true,
 terminal_progress:{since:1,alert:{version:1,state:'attention',kind:'stale',active:true,
 source:'event-1',id:'overdue',revision:20,updated_at:1900,message:'WIP overdue'}}};
const snapshot={'owner::demo':[s]},key=C.key(s);
N.update(snapshot);
assert(N.snooze(key,'overdue')&&!N.items().length,'snooze hides the exact current reminder');
assert(delay===1800000,'wake is scheduled for exactly 30 minutes');
''' + NOTIFICATIONS + r'''
N=window.LabTerminalNotifications;N.update(snapshot);
assert(!N.items().length&&N.items({history:true}).length===1,'snooze survives a page reload and retains history');
assert(C.status(s).state==='working'&&s.terminal_status.updated_at===1,'no fake progress or completion report');
now+=1800000-1;N.render();assert(!N.items().length&&delay===1,'snooze lasts the full interval');
now++;wake();assert(N.items().length===1,'timer restores the reminder without a server refresh');
assert(N.dismiss(key,'overdue')&&!N.items().length,'dismiss current reminder');
''' + NOTIFICATIONS + r'''
N=window.LabTerminalNotifications;N.update(snapshot);now+=86400000;N.render();
assert(!N.items().length&&N.items({history:true})[0].mute.until===null,'dismiss persists across reload and time');
// Another browser window can clear or replace this profile's saved choice.
const stored=values['labTerminalNotificationMutes-v1'];values['labTerminalNotificationMutes-v1']='{}';
windowEvents.storage({key:'labTerminalNotificationMutes-v1'});assert(N.items().length===1,'storage updates sync other windows');
values['labTerminalNotificationMutes-v1']=stored;windowEvents.storage({key:'labTerminalNotificationMutes-v1'});
assert(!N.items().length,'another window dismissal applies');
N.update({'owner::demo':[{...s,tmux_id:'$2'}]});
assert(N.items().length===1,'a recreated terminal does not inherit the old mute');
N.update(snapshot);s.terminal_status=report('working',30);
s.terminal_progress={since:30,alert:{...s.terminal_progress.alert,id:'next-overdue',source:'event-30',revision:40}};
N.update(snapshot);
assert(N.items().length===1&&!N.dismiss(key,'overdue')&&!N.snooze(key,'overdue'),'an old control cannot mute a new reporting interval');
s.terminal_status=report('attention',50);N.update(snapshot);
assert(N.items()[0].state==='attention'&&!N.dismiss(key,'event-50'),'actual input requests cannot be dismissed as reminders');
s.terminal_status=report('finished',60);N.update(snapshot);
assert(N.items()[0].state==='finished'&&!N.snooze(key,'event-60'),'finishes still use normal review');
console.log(JSON.stringify({passed:true}));
''')
    assert result['passed']
