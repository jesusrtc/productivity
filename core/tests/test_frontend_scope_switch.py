"""Real-browser cached folder/worktree switches must not wait on the network."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
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


def test_large_folder_and_worktree_switches_reuse_dom_under_200ms(tmp_path):
    chrome = (os.environ.get('CHROME_BIN') or shutil.which('chromium')
              or shutil.which('google-chrome')
              or '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
    node = shutil.which('node')
    if not Path(chrome).is_file() or not node:
        pytest.skip('Chrome and Node are required')
    app = (STATIC / 'js/lab-app.js').read_text()

    def between(start, end):
        return app[app.index(start):app.index(end, app.index(start))]

    helpers = '\n'.join([
        between('  function afterFirstPaint(', '  function afterPageQuiet('),
        between('  function _sidebarFolderScope(', '  async function _sidebarDiscoverWorktrees('),
        between('  function _sidebarClearWorktreeDiscovery(', '  function _sidebarValidColor('),
        between('  const _sidebarScopeViews =', '  function sidebarSetWorktreeColor('),
        between('  async function _refreshSidebarAfterFileConfig(', '  async function saveSidebarFileConfig('),
        between('  async function _refreshWorkspaceSidebar(', '  function paintWorkspaceShell('),
        between('  function _sidebarScanLabel(', '  function _sidebarFetchWorkspaceFiles('),
    ])
    checks = r'''
let currentRepo = null, currentWorkspace = {path:'/workspace', is_workspace:true};
let _sidebarFileConfig = {folderScopes:[
  {path:'/large-project',label:'Large',worktreeFolder:'/trees'},
  {path:'/small-project',label:'Small'}], selectedFolders:{'/workspace':'/large-project'},
  selectedWorktrees:{}, recentMode:'local-main', filesSort:'name'};
let showWorkspaceDotFiles = false, fileTree = [], diffCache = {};
let _workspaceDocPath = null, _workspaceDocRoot = null, workspaceOpenFile = null, _lastWorkspaceMtime = 0;
let _repoFileRoot = '', _sidebarWorktreeFolders = [{path:'/trees/branch',name:'branch'}];
let _sidebarWorktreeDiscoveryKey = 'large', _sidebarWorktreeFolderResolved = '/trees';
let _sidebarWorktreeDiscoveryPromise = null, _sidebarWorktreeDiscoveryPromiseKey = '', _sidebarWorktreeDiscoveryGeneration = 0;
const _workspaceSidebarCache = new Map(), _sidebarScanStates = new Map();
const _termCancelPendingLinkedFileOpen = () => {}, _storeSidebarFileConfig = () => {};
const _sidebarEnsureWorktrees = () => new Promise(() => {});
const selfPopulateSidebar = _sidebarEnsureWorktrees, vaultPopulateSidebar = _sidebarEnsureWorktrees, loadWorkspaceView = _sidebarEnsureWorktrees;
const _sidebarFileScopeButtonsHtml = () => '<button>Folders</button>';
const _sidebarScopedRoot = base => (_sidebarFileConfig.selectedWorktrees || {})[_sidebarWorkspaceRoot(base)] || _sidebarWorkspaceRoot(base);
const sidebar = document.getElementById('sidebar');
const assert = (value, message) => { if (!value) throw new Error(message); };
const paint = (root, large) => {
  // A large real DOM, including a retained open folder and 50,000 file rows.
  // Hidden descendants use the same CSS as the production tree.
  sidebar.innerHTML = '<div class="sidebar-scope-view"><div class="sidebar-title">' + root + '</div>' +
    '<select aria-label="File worktree" data-base-root="/workspace"><option value="">main</option><option value="/trees/branch">branch</option></select>' +
    '<div class="sidebar-folder-children open"><a class="sidebar-file">Visible file</a></div>' +
    '<div class="sidebar-folder-children">' + (large ? Array.from({length:50000}, (_,i) =>
      '<a class="sidebar-file" data-filepath="src/file' + i + '.py"><span class="sidebar-fname">file' + i + '.py</span></a>').join('') : '<a>small.py</a>') + '</div></div>';
  _workspaceSidebarCache.set('/workspace', {fileRoot:root, files:[]});
  sidebar.querySelector('select').value = _sidebarFileConfig.selectedWorktrees['/large-project'] || '';
  _sidebarMarkPainted('/workspace', root);
  return sidebar.firstElementChild;
};
const folderButton = path => ({getAttribute: name => name === 'data-base-root' ? '/workspace' : path});
const frame = () => new Promise(resolve => requestAnimationFrame(resolve));
const measurements = [];
(async () => {
  for (const surface of ['workspace','self','vault','repo']) {
    document.body.className = surface + '-active';
    currentRepo = surface === 'repo' ? '/workspace' : null;
    _sidebarFileConfig.selectedFolders = {'/workspace':'/large-project'};
    _sidebarFileConfig.selectedWorktrees = {};
    _sidebarWorktreeFolders = [{path:'/trees/branch',name:'branch'}];
    const large = paint('/large-project', true);
    await frame();
    await sidebarSelectFolder(folderButton('/small-project'));
    const small = paint('/small-project', false);
    await frame();
    const start = performance.now();
    await sidebarSelectFolder(folderButton('/large-project'));
    assert(sidebar.firstElementChild === large, surface + ': cached nodes were reconstructed');
    assert(sidebar.querySelector('.sidebar-folder-children.open'), 'expansion state lost');
    // Include layout and a rendered frame, not only function-call time.
    sidebar.getBoundingClientRect();
    await frame();
    const elapsed = performance.now() - start;
    measurements.push({surface, milliseconds:Math.round(elapsed * 10) / 10});
    assert(elapsed < 200, surface + ': switch took ' + elapsed + 'ms');
    assert(_sidebarWorktreeFolders[0]?.path === '/trees/branch', 'cached discovery was lost');
    const selectWorktree = async value => {
      const select = sidebar.querySelector('select');
      select.value = value;
      await sidebarSelectWorktree(select);
    };
    await selectWorktree('/trees/branch');
    const branch = paint('/trees/branch', false);
    await selectWorktree('');
    assert(sidebar.firstElementChild === large, 'return from worktree lost main checkout');
    assert(sidebar.querySelector('select').value === '', 'main picker has the outgoing selection');
    await selectWorktree('/trees/branch');
    assert(sidebar.firstElementChild === branch, 'worktree did not restore immediately');
    assert(sidebar.querySelector('select').value === '/trees/branch', 'branch picker has the outgoing selection');
    await sidebarSelectFolder(folderButton('/small-project'));
    assert(sidebar.firstElementChild === small, 'folder selection restored wrong tree');
    // Hidden-file settings cannot reuse an incompatible visible tree.
    showWorkspaceDotFiles = true;
    assert(!_sidebarRestoreScope('/workspace'), 'hidden-file setting reused stale DOM');
    showWorkspaceDotFiles = false;
    _sidebarScopeViews.clear();
  }
  assert(_sidebarScanLabel('refreshing') === '', 'background updates show a constant loading message');
  for (let i=0; i<12; i++) {
    _sidebarFileConfig.folderScopes.push({path:'/extra' + i,label:'Extra'});
    _sidebarFileConfig.selectedFolders = {'/workspace':'/extra' + i};
    paint('/extra' + i, false); _sidebarCacheCurrentScope('/workspace');
  }
  assert(_sidebarScopeViews.size <= 8, 'detached views are unbounded');
  document.getElementById('result').textContent = 'PASS:' + JSON.stringify(measurements);
})().catch(error => {document.getElementById('result').textContent = 'FAIL:' + error.stack;});
'''
    (tmp_path / 'switch.html').write_text(
        '<!doctype html><meta charset="utf-8"><link rel="stylesheet" href="/static/css/lab-shell.css">'
        '<style>#sidebar{width:340px;height:600px;overflow:auto}</style>'
        '<body><div id="sidebar"></div><div id="content"></div><pre id="result">PENDING</pre>'
        '<script>' + helpers + checks + '</script>')
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
            f'http://127.0.0.1:{server.server_port}/switch.html', str(tmp_path / 'rendered.html'),
            str(tmp_path / 'switch.png'),
        ], capture_output=True, text=True, timeout=25, env={**os.environ, 'LAB_UI_AUTH_COOKIE':''})
        assert result.returncode == 0, result.stderr
        rendered = (tmp_path / 'rendered.html').read_text()
    finally:
        if process:
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
    print(result[1])
