"""Real terminal context menus → API → owned tmux → persistent, closable cards."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

from core.routes import term
from lab import terminal_status
from .test_terminal_watch import report
from .test_term_creation_native import native_creation_tmux, native_creation_client  # noqa: F401
from .test_frontend_terminal_ui import ROOT, _run_node, _js_between
from .test_frontend_terminal_completion import CLOCK, MODULE
from .test_frontend_terminal_notifications import NOTIFICATIONS
from .test_frontend_project_cache import _check_project_html


def test_reminder_presets_and_tomorrow_use_the_clients_local_calendar():
    result = _run_node(CLOCK + 'document.getElementById=()=>null;' + MODULE + NOTIFICATIONS + r'''
const N=window.LabTerminalNotifications,now=new Date(2026,9,31,21,45);
for(const seconds of [600,1800,3600,7200,21600])
 assert(N.reminderTime(String(seconds),now)===now.getTime()/1000+seconds,'preset duration');
const tomorrow=new Date(N.reminderTime('tomorrow',now)*1000);
assert(tomorrow.getFullYear()===2026&&tomorrow.getMonth()===10&&tomorrow.getDate()===1
 &&tomorrow.getHours()===9&&tomorrow.getMinutes()===0,'tomorrow is local 9 AM across DST');
let rejected=false;try{N.reminderTime('arbitrary',now)}catch{rejected=true}
assert(rejected,'unknown time rejected');console.log(JSON.stringify({passed:true}));
''')
    assert result['passed']


def test_watched_working_status_preserves_the_notification_and_active_alerts():
    result = _run_node(CLOCK + 'document.getElementById=()=>null;' + MODULE + NOTIFICATIONS + r'''
const C=window.LabTerminalCompletion,N=window.LabTerminalNotifications;
const s={...session('finished'),workspace_id:'demo',vault:'owner',llm_controlled:true};
s.terminal_status.message='Tests passed';
s.terminal_watch={mode:'pin',id:'watch',report:s.terminal_status};
const snapshot={'owner::demo':[s]};N.update(snapshot);
const saved=s.terminal_watch.report;
assert(N.items()[0].state==='finished','current completion is green');
C.input(s,'continue\r');
assert(N.items()[0].state==='working'&&N.items({history:true})[0].state==='working','submitted input immediately makes watched cards yellow in both views');
s.terminal_status=report('working',2,'Implementing');N.update(snapshot);
assert(N.items()[0].state==='working'&&N.items()[0].report_id===saved.id&&N.items()[0].message===saved.message,'working changes presentation while retaining exact notification');
for(const kind of ['stale','reconnect','automation']){
 const alert={...report('attention',3,'Check status'),kind,active:true,source:s.terminal_status.id};
 const field={stale:'terminal_progress',reconnect:'terminal_recovery_alert',automation:'terminal_automation_alert'}[kind];
 s[field]=kind==='stale'?{alert}:alert;s.terminal_watch.report=alert;N.update(snapshot);
 assert(N.items()[0].state==='attention'&&N.items()[0].kind===kind,'working cannot hide active '+kind+' alert');
 delete s[field];N.update(snapshot);
 assert(N.items()[0].state==='working'&&!N.items()[0].kind,'resolved '+kind+' cannot keep a stale alert status');
}
s.terminal_watch={mode:'closed',report:saved,closed_report_id:saved.id};N.update(snapshot);
assert(!N.items().length&&N.items({history:true})[0].state==='finished','closed history retains the original event status');
assert(saved.state==='finished'&&s.terminal_status.state==='working','presentation never mutates saved notification or agent status');
console.log(JSON.stringify({passed:true}));
''')
    assert result['passed']


def test_native_terminal_watch_menu_and_notifications_in_chrome(
        native_creation_tmux, native_creation_client, seed_workspace, tmp_path):
    run, socket, _ = native_creation_tmux
    seed_workspace('demo')
    client = native_creation_client
    name = client.post('/api/term/sessions', json={'workspace_id':'demo','kind':'terminal'}).json()['name']
    initial = client.get('/api/term/sessions', params={'workspace_id':'demo'}).json()[0]

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def respond(self, status, body):
            self.send_response(status)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type')
            self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(body)

        def do_OPTIONS(self):
            self.respond(200, b'{}')

        def do_GET(self):
            response = client.get(self.path)
            self.respond(response.status_code, response.content)

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            if self.path == '/fixture/report':
                value = report(body['state'], body['revision'], body['message'])
                run('set-option','-t',name,'@lab_llm','1')
                run('set-option','-t',name,'@lab_status',terminal_status.encode(value))
                if body['state'] != 'working':
                    run('set-option','-t',name,'@lab_notification',terminal_status.encode(value))
                self.respond(200, json.dumps(value).encode())
            else:
                response = client.post(self.path, json=body)
                self.respond(response.status_code, response.content)

    server = ThreadingHTTPServer(('127.0.0.1',0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    setup = r'''
const assert=(ok,message)=>{if(!ok)throw Error(message)};
const until=async fn=>{for(let i=0;i<250;i++){if(fn())return;await new Promise(r=>setTimeout(r,10));}throw Error('Timed out '+fn)};
const errors=[],explorerToast=(message,isError)=>{if(isError)errors.push(message)};
const nativeFetch=window.fetch.bind(window);window.fetch=(url,options)=>nativeFetch(new URL(url,API),options);
let termSessions=[INITIAL],_termGroupMenuOutside=null,termSessionOrientation='horizontal',termWipOnly=true;
const _termSelectTab=()=>{},_termTabSelection=()=>new Set([termSessions[0].name]);
const _termReadGroupState=()=>({tabMembership:{},tabGroups:[]}),_termDisplayMains=()=>new Map();
const _termSessionLogical=()=>termSessions[0].logical_name,_termGroupScopeKey=()=> 'demo';
const _termSubtabParents=()=>({}),_termActiveWorkspaceId=()=> 'demo';
const termSessEsc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const tab=document.getElementById('tab');tab.addEventListener('contextmenu',event=>{event.preventDefault();termOpenTabMenu(termSessions[0].name,tab)});
async function refresh(){
 termSessions=await (await fetch('/api/term/sessions?workspace_id=demo')).json();
 const snapshot=await (await fetch('/api/workspace-documents/attention')).json();
 LabTerminalNotifications.update(snapshot);
}
let N,completed=0,opened=0;
function configure(){
 N=LabTerminalNotifications;
 N.configure({changed:refresh,open:async item=>{opened++;return termSessions[0]},error:explorerToast});
 const original=N.setWatch;N.setWatch=async(...args)=>{try{return await original(...args)}finally{completed++}};
}
function menu(){tab.dispatchEvent(new MouseEvent('contextmenu',{bubbles:true}));document.querySelector('[data-action=watch]').click();}
async function choose(choice){
 menu();const count=completed;document.querySelector('[data-action="watch:'+choice+'"]').click();
 await until(()=>completed>count);assert(!errors.length,errors.join('; '));
}
async function send(state,revision,message){await fetch('/fixture/report',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({state,revision,message})});await refresh();}
'''
    checks = r'''
(async()=>{try{
configure();await refresh();const host=document.getElementById('termNotifications');
for(const kind of ['normal','fixed','document']){
 window.LabObjectives=kind==='normal'?undefined:{terminalMain:()=>kind==='fixed'};
 if(kind==='document')termSessions[0].document_source={workspace_id:'demo'};
 menu();assert(document.querySelectorAll('[data-action^="watch:"]').length===7,'all presets on '+kind+' terminal');
 termCloseGroupMenu();delete termSessions[0].document_source;
}
window.LabObjectives=undefined;
for(const seconds of [600,1800,3600,7200,21600]){
 const before=Date.now()/1000;await choose(String(seconds));
 assert(Math.abs(termSessions[0].terminal_watch.due_at-before-seconds)<2,'saved real preset '+seconds);
 assert(!host.querySelector('[data-notification-watch-close]'),'future reminder stays quiet');
}
await choose('tomorrow');let due=new Date(termSessions[0].terminal_watch.due_at*1000);
assert(due.getHours()===9&&due.getMinutes()===0,'tomorrow local 9 AM saved by API');
await choose('cancel');assert(!termSessions[0].terminal_watch,'cancel clears server watch');
await choose('pin');
const card=()=>host.querySelector('.watched-notification');
assert(card()?.textContent.includes('Check this terminal')&&getComputedStyle(card()).backgroundColor==='rgb(106, 85, 23)','unreported shell gets a yellow manual check');
assert(!LabTerminalCompletion.status(termSessions[0]),'watch cannot invent agent status');
assert(Math.abs(host.getBoundingClientRect().top-96)<1,'pinned card stays at top');
card().click();await until(()=>opened===1);assert(card(),'opening leaves watch visible');
await send('attention',1,'Choose <branch> & review');
assert(card().textContent.includes('Choose <branch> & review')&&!card().querySelector('branch'),'newest real alert replaces pin and escapes content');
await send('working',2,'Implementing');
assert(card().textContent.includes('Choose <branch>')&&card().classList.contains('working')
 &&getComputedStyle(card()).backgroundColor==='rgb(106, 85, 23)','working retains last alert and turns yellow');
await send('finished',3,'Tests passed');LabTerminalCompletion.acknowledge('',termSessions[0]);N.render();
assert(card()?.textContent.includes('Tests passed'),'reviewing green cannot clear pinned card');
LabTerminalCompletion.input(termSessions[0],'continue\r');
assert(card().classList.contains('working')&&card().querySelector('.term-notification-icon').textContent==='…'
 &&card().querySelector('.term-notification-context').textContent.includes('Working · Pinned')
 &&card().querySelector('.term-notification-message').textContent==='Last notification: Tests passed'
 &&!card().title.includes('Finished'),'submitted input immediately replaces stale green and finished heading');
await send('working',4,'Continuing');
assert(card().classList.contains('working')&&getComputedStyle(card()).backgroundColor==='rgb(106, 85, 23)','new WIP report keeps watched card yellow');
const currentWatch=termSessions[0].terminal_watch.id;
// Recreate the entire module; data comes from the native session, not browser storage.
(0,eval)(NOTIFICATION_SOURCE);configure();await refresh();
assert(card()?.textContent.includes('Tests passed')&&card().classList.contains('working')
 &&termSessions[0].terminal_watch.id===currentWatch,'fresh module restores yellow watch and retained completion');
host.querySelector('[data-notification-watch-close]').click();await until(()=>termSessions[0].terminal_watch.mode==='closed'&&!card());
assert(!card()&&!N.items().length&&termSessions[0].terminal_status.state==='working','corner X hides exact retained alert without changing WIP status');
N.showHistory(true);assert(host.textContent.includes('Tests passed'),'closed alert remains in searchable history');N.showHistory(false);
await send('attention',5,'A new question');assert(N.items().length===1&&!card(),'closing cannot suppress a newer normal request');
const key=LabTerminalCompletion.key(termSessions[0]);
await N.setWatch(termSessions[0],'remind',{due_at:Date.now()/1000+.35});
assert(!card(),'scheduled watch remains quiet before deadline');
await until(()=>!!card());assert(card().textContent.includes('A new question'),'wake timer shows retained last alert at deadline');
host.querySelector('[data-notification-watch-close]').click();await until(()=>termSessions[0].terminal_watch.mode==='closed'&&!card());
assert(!host.querySelector('.term-notification')&&N.items({history:true}).length===1,'X closes reminder, retains history');
await choose('pin');await send('working',6,'Continuing');
assert(card()?.textContent.includes('A new question'),'final pinned latest notification survives a new working report');
for(const width of [320,400]){host.style.width=width+'px';assert(host.scrollWidth<=width+2,'close control fits narrow layout');}
assert(!errors.length,errors.join('; '));document.body.dataset.result='pass';
}catch(error){document.body.dataset.result='fail';document.body.append(String(error.stack||error));}})();
'''
    css = (ROOT / 'core/src/core/static/css/lab-shell.css').read_text()
    menus = _js_between('  function termCloseGroupMenu()', '  function termOpenDividerOptions(')
    tab_menu = _js_between('  function termOpenWatchMenu(', '  function termOpenSelectedTabsMenu(')
    html = '<!doctype html><meta charset="utf-8"><style>'+css+'''
body{--bg-primary:#0d1117;--bg-secondary:#161b22;--bg-tertiary:#21262d;--border:#30363d;--text-primary:#e6edf3;--text-secondary:#a6afb9;--accent:#58a6ff;background:#0d1117;color:#e6edf3}
</style><button id="tab">Terminal</button><div id="termGroupMenu" class="term-group-menu" role="menu" hidden></div><div id="termNotifications" class="term-notifications"></div><script>'''
    html += 'const API='+json.dumps(f'http://127.0.0.1:{server.server_port}')+',INITIAL='+json.dumps(initial)+';'
    html += 'const NOTIFICATION_SOURCE='+json.dumps(NOTIFICATIONS)+';'+setup+MODULE+NOTIFICATIONS+menus+tab_menu+checks+'</script>'
    try:
        _check_project_html(tmp_path, html, focused=True, screenshot=True)
    finally:
        server.shutdown()
        thread.join(timeout=3)
        server.server_close()
