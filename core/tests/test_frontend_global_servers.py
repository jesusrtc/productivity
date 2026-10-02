"""Native global Servers tabs, scoped edits/actions, and one error-aware Logs button."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import threading
import time

import pytest

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / 'core/src/core/static'


def test_global_servers_and_single_logs_in_chrome(tmp_path):
    chrome = (os.environ.get('CHROME_BIN') or shutil.which('chromium')
              or shutil.which('google-chrome')
              or '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
    node = shutil.which('node')
    if not Path(chrome).is_file() or not node:
        pytest.skip('Chrome and Node required')
    source = (STATIC / 'js/lab-app.js').read_text()
    helpers = source[source.index('  // Global Servers editor:'):source.index('  // ─── Client-global Assistant view')]
    html = (ROOT / 'core/src/core/templates/index.html').read_text()
    modal = html[html.index('<div class="modal-overlay" id="proxiesModal"'):html.index('<div class="doc-modal-overlay" id="docViewModal"')]
    checks = r'''
const assert=(value,message)=>{if(!value)throw Error(message);};
const until=async fn=>{for(let i=0;i<300;i++){if(fn())return;await new Promise(r=>setTimeout(r,5));}throw Error('Timed out');};
const a={is_workspace:true,name:'demo',display_name:'Demo A',path:'/vault-a/demo',vault:'a'};
const b={is_workspace:true,name:'demo',display_name:'Demo B',path:'/vault-b/demo',vault:'b'};
const empty={is_workspace:true,name:'empty',display_name:'Empty',path:'/vault-a/empty',vault:'a'};
let currentWorkspace=a, workspaceTabsAll=[a,b,empty], workspacesList=[];
const _workspaceSidebarCache=new Map(),_workspaceAttrsCache=new Map();
const _workspaceDisplayName=w=>w.display_name||w.name, _workspaceVaultId=w=>w?.vault||null;
const escapeHtml=s=>String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;');
let sidebarRefreshes=0;
function _refreshWorkspaceSidebar(){sidebarRefreshes++;}
async function workspaceTabsRefresh(){}
const requests=[];
let permit=false, deferVault='', releaseRead, releaseAction, releaseSave, failVault='';
window.confirm=()=>permit;
const config=vault=>({source:'servers.json',servers:[{name:'frontend',label:'App '+vault,host:'localhost',port:8001,path:'/',start_command:'make serve',stop_command:'make stop'}]});
window.fetch=async(url,options={})=>{
  const parsed=new URL(url,location.href);requests.push({url,options});
  if(parsed.pathname==='/api/log/error-state')return {ok:true,json:async()=>({cursor:'new-errors',exists:true,size:100})};
  if(parsed.pathname==='/api/server-config'){
    const vault=parsed.searchParams.get('vault');
    if(options.method==='PUT')return await new Promise(resolve=>{releaseSave=()=>resolve({ok:true,json:async()=>({servers:JSON.parse(options.body).servers})});});
    if(vault===failVault)throw Error('Unavailable workspace');
    const body=parsed.searchParams.get('workspace_id')==='empty'?{servers:[],source:null}:config(vault);
    if(vault===deferVault)return await new Promise(resolve=>{releaseRead=()=>resolve({ok:true,json:async()=>body});});
    return {ok:true,json:async()=>body};
  }
  if(parsed.pathname.startsWith('/api/proxies/'))return await new Promise(resolve=>{releaseAction=()=>resolve({ok:true,json:async()=>({action:'start'})});});
  throw Error('Unexpected URL '+url);
};
let logsOpened=0;
window.goToLogs=()=>logsOpened++;
'''
    assertions = r'''
(async()=>{
  await new Promise(r=>setTimeout(r,0));
  await labLogAlertRefresh();
  assert(document.querySelectorAll('.lab-log-alert').length===1,'one global Logs button');
  assert(!document.getElementById('labLogAlertButton'),'alert reused header');
  assert(document.getElementById('globalLogsBtn').classList.contains('has-unseen'),'single Logs button keeps error indicator');
  labLogAlertMarkSeen();assert(!document.getElementById('globalLogsBtn').classList.contains('has-unseen'),'review clears error indicator');
  document.getElementById('globalLogsBtn').click();assert(logsOpened===1,'one Logs navigation');
  document.getElementById('globalServersBtn').focus();await openProxiesModal();
  const overlay=document.getElementById('proxiesModal');
  const tabs=()=>[...document.querySelectorAll('#proxiesWorkspaceTabs button')];
  const active=()=>tabs().find(t=>t.getAttribute('aria-selected')==='true');
  const rows=()=>document.getElementById('proxiesRows');
  assert(tabs().length===3&&active().textContent==='Demo A','current workspace selected, all tabs included');
  assert(rows().textContent.includes('App a'),'current config');
  await selectProxyWorkspace(b.path);
  assert(currentWorkspace===a&&active().textContent==='Demo B'&&rows().textContent.includes('App b'),'global picker independent of main workspace');
  const action=proxyServerAction(rows().querySelector('article').dataset.rowId,'start');
  await until(()=>releaseAction);
  assert(tabs().every(t=>t.disabled),'mutating server locks scope');
  assert(!(await selectProxyWorkspace(a.path)),'scope cannot move during action');
  const actionRequest=requests.find(r=>r.url.startsWith('/api/proxies/'));
  assert(actionRequest.url==='/api/proxies/demo/frontend/start?vault=b','action captured exact vault');
  releaseAction();await action;
  editProxyRow(rows().querySelector('article').dataset.rowId);
  assert(!(await selectProxyWorkspace(a.path))&&active().textContent==='Demo B','dirty edits require discard');
  permit=true;deferVault='a';const oldRead=selectProxyWorkspace(a.path);await until(()=>releaseRead);
  const releaseOld=releaseRead;deferVault='';await selectProxyWorkspace(empty.path);
  releaseOld();await oldRead;
  assert(active().textContent==='Empty'&&rows().querySelector('.proxies-empty'),'late response cannot repaint new tab');
  failVault='b';await selectProxyWorkspace(b.path);
  assert(document.getElementById('proxiesSaveBtn').disabled&&document.getElementById('proxiesAddBtn').disabled&&document.getElementById('proxiesCreateBtn').disabled,'failed config cannot overwrite unseen file');
  failVault='';await reloadProxyConfig();assert(!document.getElementById('proxiesSaveBtn').disabled,'reload recovers');
  editProxyRow(rows().querySelector('article').dataset.rowId);
  rows().querySelector('[data-field="label"]').value='New App B';
  const save=submitProxies({preventDefault(){}});await until(()=>releaseSave);
  assert(!(await selectProxyWorkspace(a.path)),'save locks scope');
  const saved=requests.find(r=>r.options.method==='PUT');
  assert(new URL(saved.url,location.href).searchParams.get('vault')==='b'&&JSON.parse(saved.options.body).servers[0].label==='New App B','save uses selected workspace');
  releaseSave();await save;
  assert(!overlay.classList.contains('active')&&sidebarRefreshes===0,'saving another workspace leaves visible sidebar alone');
  await openProxiesModal();assert(active().textContent==='Demo A','reopen selects current workspace');
  closeProxiesModal();assert(document.activeElement.id==='globalServersBtn','focus returns to global trigger');
  currentWorkspace=null;await openProxiesModal();assert(active(),'global opening outside workspace');closeProxiesModal();
  currentWorkspace=a;await openProxiesModal();
  const box=overlay.querySelector('.proxies-modal');assert(box.scrollWidth<=box.clientWidth,'modal fits viewport');
  assert(box.getBoundingClientRect().left>10,'modal centered');
  // A running backend may still serve the previous template during an update.
  document.getElementById('globalLogsBtn').removeAttribute('onclick');
  await new Promise((resolve,reject)=>{const script=document.createElement('script');script.src='/static/js/lib/log-alert.js';script.onload=resolve;script.onerror=reject;document.head.append(script);});
  document.getElementById('globalLogsBtn').click();assert(logsOpened===2,'older shell receives one navigation handler');
  assert(document.querySelectorAll('.lab-log-alert').length===1,'older shell also retains a single Logs control');
  document.getElementById('result').textContent='PASS: global tabs, active scope, stale reads, scoped actions and saves, one Logs button';
})().catch(error=>{document.getElementById('result').textContent='FAIL: '+error.stack;});
'''
    page = ('<!doctype html><meta charset="utf-8"><style>:root{--bg-primary:#0d1117;'
            '--bg-secondary:#161b22;--bg-tertiary:#21262d;--border:#30363d;--text-primary:#e6edf3;'
            '--text-secondary:#8b949e;--text-dim:#484f58;--accent:#58a6ff;--red:#f85149;--green:#3fb950}'
            '*{box-sizing:border-box}body{margin:0;font-family:system-ui;background:#0d1117;color:#fff}'
            '.topbar{display:flex;gap:12px;padding:12px}.theme-toggle{padding:6px 12px}</style>'
            '<link rel="stylesheet" href="/static/css/lab-shell.css">'
            '<div class="topbar"><button id="globalServersBtn" onclick="openProxiesModal()">Servers</button>'
            '<button id="globalLogsBtn" onclick="goToLogs()"><span class="lab-log-dot"></span><span class="lab-log-label">Logs</span></button>'
            '<button id="settingsBtn">Settings</button></div><pre id="result">PENDING</pre>'
            + modal + '<script>' + checks + helpers + '</script>'
            '<script src="/static/js/lib/log-alert.js"></script><script>' + assertions + '</script>')
    (tmp_path / 'index.html').write_text(page)
    (tmp_path / 'static').symlink_to(STATIC, target_is_directory=True)
    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(SimpleHTTPRequestHandler, directory=tmp_path))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    profile = tmp_path / 'chrome-profile'
    process = None
    try:
        process = subprocess.Popen([
            chrome, '--headless', '--disable-gpu', '--no-sandbox', '--no-first-run',
            '--no-default-browser-check', '--disable-background-networking',
            '--user-data-dir=' + str(profile), '--remote-debugging-port=0', 'about:blank',
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
        deadline = time.monotonic() + 10
        while not (profile / 'DevToolsActivePort').exists():
            assert process.poll() is None and time.monotonic() < deadline, 'Chrome did not start'
            time.sleep(.05)
        result = subprocess.run([
            node, str(ROOT / 'scripts/chrome-dump-auth.mjs'), str(profile),
            f'http://127.0.0.1:{server.server_port}/', str(tmp_path / 'rendered.html'),
            str(tmp_path / 'servers.png'),
        ], capture_output=True, text=True, timeout=20, env={**os.environ, 'LAB_UI_AUTH_COOKIE': ''})
        assert result.returncode == 0, result.stderr
        rendered = (tmp_path / 'rendered.html').read_text()
    finally:
        if process is not None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            process.communicate(timeout=5)
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    result = re.search(r'<pre id="result">(.*?)</pre>', rendered, re.S)
    assert result and result[1].startswith('PASS:'), result[1] if result else rendered[-1000:]
