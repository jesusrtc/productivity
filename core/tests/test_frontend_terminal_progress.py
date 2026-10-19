from .test_frontend_terminal_ui import ROOT
from .test_frontend_project_cache import _check_project_html
from .test_frontend_terminal_completion import MODULE
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
 toggle.click();const row=N.items()[0];await N.open(row.key,row.report_id);
 assert(opened===1&&toggle.getAttribute('aria-checked')==='true'&&N.items().length===1,'click keeps alert and show-all');
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
 session.terminal_progress.alert.active=true;N.update(snapshot);
 document.body.dataset.result='pass';
}catch(error){document.body.dataset.result='fail';document.body.append(String(error.stack||error));}})();
'''
    css = (ROOT / 'core/src/core/static/css/lab-shell.css').read_text()
    html = '<!doctype html><meta charset="utf-8"><style>:root{--bg-primary:#0d1117;--bg-secondary:#161b22;--bg-tertiary:#21262d;--border:#30363d;--text-primary:#c9d1d9;--text-secondary:#8b949e;--accent:#58a6ff;}body{background:#0d1117;color:#c9d1d9}</style><style>' + css + '</style><body><nav id="toolbar"></nav><button id="outside">Outside</button><div id="termNotifications" class="term-notifications"></div><script>' + setup + MODULE + NOTIFICATIONS + checks + '</script>'
    _check_project_html(tmp_path, html, focused=True, screenshot=True)
