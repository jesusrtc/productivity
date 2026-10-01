from pathlib import Path
import os
import shutil
import signal
import subprocess
import time

import pytest


def test_project_cache_uses_server_age_and_ignores_outgoing_responses():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is required')
    source = (Path(__file__).resolve().parents[1] / 'src/core/static/js/lib/project-sidebar.js').read_text()
    checks = r'''
const assert = require('node:assert/strict');
let now = 1000000, active = true;
Date.now = () => now;
global.document = {hidden:false};
const timers=[], requests=[], updates=[];
global.setTimeout = callback => timers.push(callback);
global.fetch = url => new Promise(resolve => requests.push({url,resolve}));
const tick = () => new Promise(resolve => setImmediate(resolve));
const reply = async data => { requests.at(-1).resolve({ok:true,status:200,json:async()=>data}); await tick(); };
(async()=>{
  ProjectSidebar.read('/a', data=>updates.push(data), ()=>active);
  ProjectSidebar.read('/a', ()=>{}, ()=>active);
  assert.equal(requests.length,1,'in-flight requests are shared');
  await reply({entries:['old'],cache:{updated:(now-59900)/1000}});
  assert.equal(updates.length,1);
  now+=200;
  ProjectSidebar.read('/a', data=>updates.push(data), ()=>active);
  assert.equal(updates.at(-1).entries[0],'old','stale data paints immediately');
  assert.equal(requests.length,2,'browser must honor server age, not restart its TTL');
  active=false;
  await reply({entries:['new'],cache:{updated:now/1000}});
  assert.equal(updates.at(-1).entries[0],'old','outgoing request must not repaint');
  active=true;
  ProjectSidebar.read('/a', data=>updates.push(data), ()=>active);
  assert.equal(updates.at(-1).entries[0],'new');
  assert.equal(requests.length,2,'returning to a cached scope is immediate');
  now+=61000;
  ProjectSidebar.read('/a', ()=>{}, ()=>active);
  await reply({entries:['new'],cache:{updated:(now-61000)/1000,refreshing:true}});
  assert.equal(timers.length,1);
  active=false; await timers[0]();
  assert.equal(requests.length,3,'inactive scopes stop polling');
  active=true;
  for(let i=0;i<70;i++) {
    ProjectSidebar.read('/bounded/'+i,()=>{},()=>active);
    await reply({entries:[],cache:{updated:now/1000}});
  }
  ProjectSidebar.read('/a',()=>{},()=>active);
  assert.equal(requests.at(-1).url,'/a','response retention is bounded');
  console.log('PASS');
})().catch(error=>{console.error(error);process.exitCode=1;});
'''
    result = subprocess.run([node, '-e', source + checks], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert 'PASS' in result.stdout


def test_project_mount_rejects_an_outgoing_scope_before_touching_the_dom():
    from .test_frontend_terminal_ui import _js_between, _run_node
    source = _js_between('  function _sidebarProjectView(', '  function _sidebarProjectDirectory(')
    result = _run_node(r'''
const _sidebarWorktreeBaseRoot=()=>'/new', _sidebarScopedRoot=()=>'/new/feature';
const document={getElementById:()=>{throw Error('Obsolete scope touched the DOM');}};
''' + source + r'''
console.log(JSON.stringify([
  _sidebarProjectView('/old','/old/feature'),
  _sidebarProjectView('/new','/new/old-worktree')
]));
''')
    assert result == [False, False]


def test_workspace_refresh_cannot_replace_a_new_repository_view():
    from .test_frontend_terminal_ui import _js_between, _run_node
    source = _js_between('  let _workspaceSidebarRefreshSequence =', '  function paintWorkspaceShell()')
    result = _run_node(r'''
let currentWorkspace = {path:'/workspace',is_workspace:true}, currentRepo = null, showWorkspaceDotFiles = false;
const sidebar = {scrollTop:0,innerHTML:'Repository files'};
const document = {getElementById:()=>sidebar,body:{classList:{contains:()=>false}}};
let release;
const _sidebarEnsureWorktrees = () => new Promise(resolve=>{release=resolve;});
const _sidebarScopedRoot = () => {throw Error('Outgoing workspace looked up the new repository scope');};
''' + source + r'''
(async()=>{
  const pending = _refreshWorkspaceSidebar();
  currentRepo = '/repository';
  release(); await pending;
  console.log(JSON.stringify({html:sidebar.innerHTML}));
})().catch(error=>{console.error(error);process.exitCode=1;});
''')
    assert result == {'html':'Repository files'}


def test_project_file_click_uses_the_repository_reader_in_repository_mode():
    from .test_frontend_terminal_ui import _js_between, _run_node
    source = _js_between('  function _sidebarHandleFileAction(', "  document.getElementById('sidebar')?.addEventListener('click'")
    result = _run_node(r'''
let currentRepo='/project';
const calls=[];
const openWorkspaceFile=path=>calls.push(['repo',path]);
const openWorkspaceDocFromFileClick=(path,options)=>calls.push(['workspace',path,options.root]);
const row={getAttribute:name=>name==='data-filepath'?'src/file.c':'/project'};
const event={type:'click',currentTarget:{contains:()=>true},target:{closest:selector=>selector==='.sidebar-file[data-open-file]'?row:null}};
''' + source + r'''
_sidebarHandleFileAction(event);
currentRepo=null;
_sidebarHandleFileAction(event);
console.log(JSON.stringify(calls));
''')
    assert result == [['repo', 'src/file.c'], ['workspace', 'src/file.c', '/project']]


def test_project_sidebar_repairs_replaced_children_in_chrome(tmp_path):
    chrome = os.environ.get('CHROME_BIN') or shutil.which('chromium') or '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
    if not Path(chrome).is_file() or not shutil.which('node'):
        pytest.skip('Chrome and Node are required')
    from .test_frontend_terminal_ui import _js_between

    source = _js_between('  let _sidebarProjectGeneration =', '  // Keep the actual nodes:')
    prelude = r'''
const assert = (value, message) => { if (!value) throw Error(message); };
const requests = [], _sidebarScopeViews = new Map();
const _sidebarScopeTransition = null;
let currentRepo = null, showWorkspaceDotFiles = false, _workspaceDocPath = null, _workspaceDocRoot = null;
const _sidebarFileConfig = {recentMinutes:60};
const _sidebarWorktreeBaseRoot = () => '/workspace';
const _sidebarScopedRoot = () => '/workspace/repo';
const _sidebarMarkPainted = () => {};
const escAttr = value => value, esc = value => value;
const _sidebarFileConfigCogHtml = () => '';
const _sidebarRecentSelectorsHtml = () => '<div class="sidebar-recent-selectors"></div>';
const _sidebarFileScopeButtonsHtml = () => '';
const _sidebarWorktreePickerHtml = () => '';
const _sidebarFilesTitle = () => '<div>Files</div>';
const _sidebarCurrentRecentMode = () => 'none';
const _sidebarCurrentSortMode = () => 'name';
const _sidebarRecentSelectorValue = () => 'none';
const _sidebarCompareFiles = (a,b) => a.path.localeCompare(b.path);
const renderSidebarFileTree = tree => '<a class="sidebar-file">' + tree.__files__[0].path + '</a>';
const ProjectSidebar = {read(url, update, current) { if(current()) requests.push({url,update,current}); }};
window.setInterval = () => 1;
'''
    checks = r'''
try {
  const sidebar = document.getElementById('sidebar');
  assert(_sidebarProjectView('/workspace','/workspace/repo'), 'project mounts');
  const original = sidebar.firstElementChild, pending = requests[0];
  assert(pending.current(), 'fresh directory owns its request');
  // A normal workspace renderer replaced the contents of a reused container.
  original.innerHTML = '<div>Normal workspace files</div>';
  _sidebarProjectRefresh();
  _sidebarProjectDirectory(null, original);
  _sidebarProjectDirectory(null, null);
  assert(!pending.current(), 'detached directory must reject its old result');
  assert(_sidebarProjectView('/workspace','/workspace/repo'), 'incomplete view repairs');
  const repaired = sidebar.firstElementChild;
  assert(repaired !== original, 'repair replaces stale project ownership');
  assert(repaired.querySelector('[data-project-directory="."]'), 'root directory restored');
  const next = requests.at(-1);
  next.update({entries:[{path:'README.md',type:'file'}]});
  assert(repaired.querySelector('.sidebar-file').textContent === 'README.md', 'repaired files publish');
  // A connected node moved to another view cannot paint through its old owner.
  const root = repaired.querySelector('[data-project-directory="."]');
  document.getElementById('other').append(root);
  assert(root.isConnected && !next.current(), 'containment rejects a moved directory');
  _sidebarProjectRefresh();
  sidebar.innerHTML = '<div class="sidebar-scope-view">Normal workspace</div>';
  _sidebarProjectRefresh();
  assert(!next.current(), 'normal replacement cancels project callbacks');
  document.body.dataset.result = 'pass';
} catch(error) {
  document.body.dataset.result = 'fail';
  document.body.append(String(error.stack || error));
}
'''
    _check_project_html(tmp_path, '<div id="sidebar"></div><div id="other"></div><script>' + prelude + source + checks + '</script>')


def _check_project_html(tmp_path, html):
    chrome = os.environ.get('CHROME_BIN') or shutil.which('chromium') or '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
    if not Path(chrome).is_file() or not shutil.which('node'):
        pytest.skip('Chrome and Node are required')
    page = tmp_path / 'project-sidebar.html'
    page.write_text(html)
    profile = tmp_path / 'chrome'
    root = Path(__file__).resolve().parents[2]
    rendered = tmp_path / 'rendered.html'
    browser = subprocess.Popen([chrome, '--headless=new', '--no-first-run', '--disable-background-networking',
                                '--user-data-dir=' + str(profile), '--remote-debugging-port=0', 'about:blank'],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    try:
        deadline = time.monotonic() + 10
        while not (profile / 'DevToolsActivePort').exists():
            assert browser.poll() is None and time.monotonic() < deadline, 'Chrome did not start'
            time.sleep(.05)
        result = subprocess.run(['node', str(root / 'scripts/chrome-dump-auth.mjs'), str(profile),
                                 page.as_uri(), str(rendered)], env={**os.environ, 'LAB_UI_AUTH_COOKIE':''},
                                capture_output=True, text=True, timeout=25)
        assert result.returncode == 0, result.stderr
        assert 'data-result="pass"' in rendered.read_text(), rendered.read_text()[-2000:]
    finally:
        if browser.poll() is None:
            os.killpg(browser.pid, signal.SIGTERM)
        browser.wait(timeout=5)


def test_cold_scope_switch_publishes_both_sections_and_rejects_cancelled_reads(tmp_path):
    from .test_frontend_terminal_ui import _js_between
    source = _js_between('  let showDotFiles = false;', '  function filterDotFiles(nodes)')
    prelude = r'''
let currentRepo=null, currentWorkspace={path:'/workspace',is_workspace:true,repos:[]};
let _workspaceDocRoot='/old', _workspaceDocPath='old.txt', workspaceOpenFile=null;
let fileTree=[], diffCache={}, _repoFileRoot=null, _lastWorkspaceMtime=0;
const _workspaceSidebarCache=new Map(), requests=[];
const esc=String, escAttr=String, _termCancelPendingLinkedFileOpen=()=>{};
const _sidebarFilesTitle=()=>'<div>Files</div>';
const _treeIsOpen=()=>false;
const renderSidebarFileTree=tree=>'<a class="sidebar-file">'+tree.__files__[0].path+'</a>';
const ProjectSidebar={read(url,update,current){if(current())requests.push({url,update,current});}};
const afterFirstPaint=callback=>callback();
window.setInterval=()=>1;
'''
    checks = r'''
const assert=(value,message)=>{if(!value)throw Error(message);};
_refreshSidebarAfterFileConfig=async()=>_sidebarProjectView('/workspace',_sidebarScopedRoot('/workspace'));
_sidebarRecentSectionHtml=files=>files.map(file=>'<a class="sidebar-file">'+file.path+'</a>').join('');
_sidebarFileConfig=_sidebarNormalizeFileConfig({recentMode:'local-main',selectedFolders:{'/workspace':'/old'},
  pinnedScopes:['/old','/new','/trees/topic'], folderScopes:[{path:'/old',label:'Old'},
    {path:'/new',label:'New'},{path:'/trees/topic',label:'New/topic',kind:'worktree'}]});
const sidebar=document.getElementById('sidebar'),content=document.getElementById('content');
sidebar.innerHTML='<div class="sidebar-scope-view">'+_sidebarFileScopeButtonsHtml('/workspace')+'<a class="sidebar-file" onclick="window.staleAction=true">old.txt</a></div>';
content.innerHTML='<p>Keep my open document</p>';
const button=path=>({getAttribute:name=>name==='data-base-root'?'/workspace':path});
const respond=(request,data)=>{if(request.current())request.update(data);};
const directory=(prefix)=>requests.find(request=>request.url.startsWith('/api/sidebar-directory')&&request.url.includes(encodeURIComponent(prefix)));
const recent=(prefix)=>requests.find(request=>request.url.startsWith('/api/sidebar-recent-files')&&request.url.includes(encodeURIComponent(prefix)));
const entries=path=>({entries:[{path,type:'file',git_tracked:true}],total:1});
(async()=>{
  _sidebarProjectView('/workspace','/old');
  respond(directory('/old'),entries('old.txt'));
  respond(recent('/old'),entries('old-change.txt'));
  sidebar.querySelector('.sidebar-file').onclick=()=>window.staleAction=true;
  const oldView=sidebar.firstElementChild,oldContent=content.firstElementChild;
  await sidebarSelectFolder(button('/new'));
  assert(sidebar.firstElementChild===oldView&&content.firstElementChild===oldContent,'cold selection blanks the view');
  assert(_workspaceDocPath==='old.txt'&&content.inert,'outgoing document ownership stays until commit');
  assert(sidebar.querySelector('.sidebar-scope-spinner'),'loading indicator missing');
  sidebar.querySelector('.sidebar-file').click();
  assert(!window.staleAction,'outgoing file action ran against the new scope');
  respond(directory('/new'),entries('new.txt'));
  assert(sidebar.firstElementChild===oldView,'directory published before recent files');
  const obsoleteRecent=recent('/new');
  await sidebarSelectFolder(button('/trees/topic'));
  const obsoleteDirectory=directory('/trees/topic');
  await sidebarSelectFolder(button('/old'));
  assert(sidebar.firstElementChild===oldView&&!content.inert&&!sidebar.querySelector('.sidebar-scope-spinner'),'cached return did not cancel loading');
  respond(obsoleteRecent,entries('obsolete.txt'));
  respond(obsoleteDirectory,entries('obsolete-tree.txt'));
  assert(sidebar.firstElementChild===oldView,'cancelled response stole the restored view');
  await sidebarSelectFolder(button('/trees/topic'));
  const retryDirectory=requests.filter(request=>request.url.startsWith('/api/sidebar-directory')).at(-1);
  respond(retryDirectory,{error:'Temporary read failure'});
  assert(sidebar.firstElementChild===oldView,'failed read discarded the outgoing tree');
  assert(sidebar.querySelector('.sidebar-scope-load-error button')&&!sidebar.querySelector('.sidebar-scope-spinner'),'retry UI missing');
  sidebarRetryScopeSwitch(sidebar.querySelector('.sidebar-scope-load-error button'));
  const newestDirectory=requests.filter(request=>request.url.startsWith('/api/sidebar-directory')).at(-1);
  const newestRecent=requests.filter(request=>request.url.startsWith('/api/sidebar-recent-files')).at(-1);
  assert(newestDirectory!==retryDirectory&&sidebar.querySelector('.sidebar-scope-spinner'),'retry did not start a fresh request');
  respond(newestRecent,entries('topic-change.txt'));
  assert(sidebar.firstElementChild===oldView,'recent files published before directory');
  respond(newestDirectory,entries('topic.txt'));
  assert(sidebar.firstElementChild.dataset.projectSidebar==='/trees/topic','ready worktree did not publish');
  assert(sidebar.querySelector('[data-project-directory]').textContent==='topic.txt','directory missing at commit');
  assert(sidebar.querySelector('[data-project-recent]').textContent==='topic-change.txt','recent files missing at commit');
  assert(!content.inert&&!sidebar.hasAttribute('aria-busy')&&!sidebar.querySelector('.sidebar-scope-spinner'),'loading state survived commit');
  assert(_workspaceDocPath===null&&_workspaceDocRoot===null,'old document ownership survived new scope');
  // A terminal can open an incoming document before the sidebar is ready.
  await sidebarSelectFolder(button('/new'));
  content.innerHTML='<p>Newer terminal-linked document</p>';
  _workspaceDocRoot='/new';_workspaceDocPath='new.txt';
  respond(requests.filter(request=>request.url.startsWith('/api/sidebar-directory')).at(-1),entries('new.txt'));
  respond(requests.filter(request=>request.url.startsWith('/api/sidebar-recent-files')).at(-1),entries('new-change.txt'));
  assert(content.textContent==='Newer terminal-linked document'&&_workspaceDocPath==='new.txt','late sidebar commit erased a newer document');
  _sidebarScopeViews.clear();
  await sidebarSelectFolder(button('/trees/topic'));
  currentWorkspace={path:'/different',is_workspace:true,repos:[]};
  _sidebarActivateFileConfig();
  assert(!_sidebarScopeTransition&&!content.inert,'leaving the workspace retained a pending loading lock');
  document.body.dataset.result='pass';
})().catch(error=>{document.body.dataset.result='fail';document.body.append(String(error.stack||error));});
'''
    _check_project_html(tmp_path, '<div id="sidebar"></div><div id="content"></div><script>' + prelude + source + checks + '</script>')
