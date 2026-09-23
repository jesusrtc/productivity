"""Real-browser ordering and race checks with deliberately stalled Git requests."""
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


def test_history_progressive_loading_keeps_local_diff_usable(tmp_path):
    chrome = (os.environ.get('CHROME_BIN') or shutil.which('chromium')
              or shutil.which('google-chrome')
              or '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
    node = shutil.which('node')
    if not Path(chrome).is_file() or not node:
        pytest.skip('Chrome and Node are required')
    app = (STATIC / 'js/lab-app.js').read_text()
    start = app.index('  function _explorerHistoryShell(')
    end = app.index('  window.closeExplorerHistory = closeExplorerHistory;', start)
    helpers = app[start:end]
    checks = r'''
let _explorerHistoryState = null, _explorerHistoryRequest = 0;
const esc = value => String(value).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;');
const escAttr = esc, activateNotebookScripts = () => {};
const renderUnified = file => '<pre>' + esc(file.patch || '') + '</pre>';
const _explorerResponseError = async response => (await response.json()).detail;
const assert = (value, message) => { if (!value) throw new Error(message); };
const tick = () => new Promise(resolve => setTimeout(resolve, 0));
const requests = [];
window.fetch = (url, {signal} = {}) => new Promise((resolve, reject) => {
  const request = {url, signal, resolve, reject, done:false};
  requests.push(request);
  signal?.addEventListener('abort', () => { request.aborted = true; reject(new DOMException('Aborted', 'AbortError')); });
});
const pending = pattern => requests.find(request => !request.done && !request.aborted && request.url.includes(pattern));
const reply = async (pattern, data, ok=true) => {
  const request = pending(pattern);
  assert(request, 'missing request: ' + pattern);
  request.done = true;
  request.resolve({ok, json:async () => data});
  await tick();
};
const commits = (start, count) => Array.from({length:count}, (_, i) => ({
  sha: String(start+i).padStart(40,'a'), message:'Commit ' + (start+i), author:'Contributor', relative_date:'2 days ago',
}));
const patch = text => ({files:[{filename:'src/large-project.js',status:'modified',additions:1,deletions:1,patch:text}]});
const page = (items, next, more, older=true) => ({commits:items,revision:'a'.repeat(40),next_offset:next,has_more:more,can_load_older:older});
const rail = document.getElementById('explorerHistoryList');
const diff = document.getElementById('explorerHistoryDiff');
const row = sha => [...rail.querySelectorAll('[data-sha]')].find(el => el.dataset.sha === sha);
(async () => {
  openExplorerHistory({root:'/large-project',path:'src/large-project.js'});
  assert(pending('phase=commits').url.includes('limit=20'), 'first page was not bounded');
  const localStart = performance.now();
  await reply('phase=working-tree', {commits:[{sha:'WORKTREE',kind:'working-tree',message:'Uncommitted changes',states:['unstaged']}]});
  await reply('sha=WORKTREE', patch('LOCAL CHANGES READY'));
  assert(diff.textContent.includes('LOCAL CHANGES READY'), 'local diff waits on log');
  assert(pending('phase=commits'), 'log must still be stalled');
  assert(rail.textContent.includes('Loading recent commits'), 'loading is not independent');
  const localMs = performance.now() - localStart;
  await reply('phase=commits', page(commits(1,20),20,true));
  assert(row('WORKTREE').classList.contains('active'), 'local selection was reset');
  row(commits(3,1)[0].sha).click();
  await reply('sha=' + commits(3,1)[0].sha, patch('SELECTED COMMIT'));
  const selectedNode = diff.firstElementChild;
  const beforeCount = requests.length;
  rail.scrollTop = 100;
  const loading = _explorerHistoryLoadMore(_explorerHistoryState);
  _explorerHistoryLoadMore(_explorerHistoryState);
  assert(requests.length === beforeCount + 1, 'duplicate page requests');
  assert(pending('phase=commits').url.includes('offset=20'), 'wrong page offset');
  assert(pending('phase=commits').url.includes('revision=' + 'a'.repeat(40)), 'history was not pinned');
  await reply('phase=commits', {detail:'History temporarily unavailable'}, false);
  await loading;
  assert(diff.firstElementChild === selectedNode, 'error replaced selected diff');
  assert(rail.textContent.includes('Retry loading commits'), 'missing retry');
  rail.querySelector('.explorer-history-more').click();
  await reply('phase=commits', page(commits(21,2),22,false));
  assert(diff.firstElementChild === selectedNode && rail.scrollTop === 100, 'appending moved diff or list');
  assert(row(commits(3,1)[0].sha).classList.contains('active'), 'appending lost selected revision');
  assert(rail.textContent.includes('older than 60 days'), 'older history inaccessible');
  rail.querySelector('.explorer-history-more').click();
  assert(pending('phase=commits').url.includes('since=0'), 'older range was not expanded');
  assert(pending('phase=commits').url.includes('offset=22'), 'older range restarted from top');
  await reply('phase=commits', page(commits(23,1),23,false,false));
  assert(rail.textContent.includes('End of history'), 'missing end marker');
  assert(!rail.querySelector('.explorer-history-more'), 'no terminal page state');

  // A selected diff and a pending page belong to one modal session only.
  row(commits(4,1)[0].sha).click();
  const abandoned = pending('sha=' + commits(4,1)[0].sha);
  openExplorerHistory({root:'/other-project',path:'other.txt'});
  assert(abandoned.signal.aborted, 'switch did not abort old diff');
  abandoned.resolve({ok:true,json:async () => patch('STALE')});
  await reply('phase=commits', page(commits(90,1),1,false,false));
  await reply('phase=working-tree', {commits:[]});
  await reply('sha=' + commits(90,1)[0].sha, patch('OTHER PROJECT'));
  assert(!diff.textContent.includes('STALE'), 'old diff painted over new modal');
  assert(diff.textContent.includes('OTHER PROJECT'), 'clean file did not select latest commit');
  openExplorerHistory({root:'/third-project',path:'third.txt'});
  const closing = pending('phase=commits');
  closeExplorerHistory();
  assert(closing.signal.aborted, 'close did not abort history request');
  await tick();
  assert(_explorerHistoryState === null, 'closed session was revived');

  // Repository history must not wait on either history or the base diff.
  const repoStart = requests.length;
  openRepositoryHistory({root:'/large-project',label:'Feature branch'});
  assert(row('WORKTREE').classList.contains('active'), 'repository did not start with local work');
  assert(!requests.slice(repoStart).some(request => request.url.includes('type=branch')), 'base diff fetched eagerly');
  await reply('type=uncommitted', patch('REPOSITORY LOCAL CHANGES'));
  assert(pending('phase=commits') && diff.textContent.includes('REPOSITORY LOCAL CHANGES'), 'repository waits on log');
  row('BRANCH').click();
  assert(pending('type=branch'), 'base diff unavailable on selection');
  await reply('type=branch', {...patch('BASE COMPARISON'),branch:'feature',base_branch:'main'});
  await reply('phase=commits', page(commits(1,20),20,true));
  assert(diff.textContent.includes('BASE COMPARISON'), 'late history reset base comparison');
  // Exercise automatic page loading as the user approaches the bottom.
  rail.scrollTop = rail.scrollHeight;
  rail.dispatchEvent(new Event('scroll'));
  assert(pending('phase=commits')?.url.includes('offset=20'), 'scroll did not load next page');
  await reply('phase=commits', page(commits(21,1),21,false));
  row('WORKTREE').click();
  document.getElementById('result').textContent = 'PASS:' + JSON.stringify({localRenderMs:Math.round(localMs),checks:'local-first, paging, retries, selection, cancellation, lazy base diff'});
})().catch(error => {document.getElementById('result').textContent = 'FAIL:' + error.stack;});
'''
    (tmp_path / 'history.html').write_text(
        '<!doctype html><meta charset="utf-8"><link rel="stylesheet" href="/static/css/lab-shell.css">'
        '<style>:root{--bg-primary:#0c1117;--bg-secondary:#171c23;--bg-tertiary:#212832;--border:#30363d;--text-primary:#e6edf3;--text-dim:#8b949e;--text-secondary:#aaa;--accent:#58a6ff;--yellow:#d29922;--purple:#b392f0}body{background:#0c1117;color:#e6edf3;font:14px sans-serif}#explorerHistoryModal{padding:16px}.explorer-history-box{height:650px}</style>'
        '<body><div id="explorerHistoryModal"><div class="explorer-history-box"><h3 id="explorerHistoryTitle"></h3>'
        '<div class="explorer-history-body"><div id="explorerHistoryFiles" class="explorer-history-files"></div>'
        '<div id="explorerHistoryDiff" class="explorer-history-diff"></div><div id="explorerHistoryList" class="explorer-history-list"></div></div></div></div>'
        '<pre id="result">PENDING</pre><script>' + helpers + checks + '</script>')
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
            f'http://127.0.0.1:{server.server_port}/history.html', str(tmp_path / 'rendered.html'),
            str(tmp_path / 'history.png'),
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
