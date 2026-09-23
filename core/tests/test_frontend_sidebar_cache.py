"""The sidebar template cache preserves DOM behavior and has hard memory bounds."""
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import time

import pytest
from .test_frontend_terminal_ui import _js_between, _run_node

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize('repaint', [False, True])
@pytest.mark.parametrize('state', ['fresh', 'stale', 'missing', 'changed-scope'])
def test_retained_rows_refresh_git_without_repainting_fresh_cache(repaint, state):
    helper = _js_between('  async function _sidebarGitStatusRefresh(',
                         '  // Parsing thousands of file rows')
    result = _run_node('''
const repaint = REPAINT, state = STATE;
let currentWorkspace = {path:'/alpha', is_workspace:true};
let root = '/alpha', _gitStatusInFlight = false;
const _GIT_STATUS_MIN_MS = 5000, _gitStatusByPath = new Map();
const _sidebarScopedRoot = () => root;
const painted = [], requests = [];
const _sidebarApplyGitStatus = entry => painted.push(entry.files);
if(state !== 'missing') _gitStatusByPath.set(root, {
  files:{'a.md':'M'}, ignored:[], ts:state==='fresh' ? Date.now() : 0,
});
const fetch = async url => {
  requests.push(url);
  if(state==='changed-scope') root='/worktree';
  return {ok:true,json:async()=>({files:{'a.md':'A'},ignored:['tmp/']})};
};
'''.replace('REPAINT', str(repaint).lower()).replace('STATE', repr(state)) + helper + '''
(async()=>{
  await _sidebarGitStatusRefresh({repaint});
  console.log(JSON.stringify({painted,requests,inFlight:_gitStatusInFlight,
    cached:_gitStatusByPath.get('/alpha')}));
})();
''')
    expected = [{'a.md': 'M'}] if repaint and state != 'missing' else []
    if state not in ('fresh', 'changed-scope'):
        expected.append({'a.md': 'A'})
    assert result['painted'] == expected
    assert len(result['requests']) == (state != 'fresh')
    assert result['inFlight'] is False
    assert result['cached']['files'] == {'a.md': 'M' if state == 'fresh' else 'A'}


def test_sidebar_template_cache_in_chrome(tmp_path):
    chrome = (os.environ.get('CHROME_BIN') or shutil.which('chromium')
              or '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
    node = shutil.which('node')
    if not Path(chrome).is_file() or not node:
        pytest.skip('Chrome and Node required')
    source = (ROOT / 'core/src/core/static/js/lab-app.js').read_text()
    start = source.index('  const _sidebarMarkupCache =')
    helper = source[start:source.index('  // Re-renders just the workspace file sidebar', start)]
    checks = r'''
const assert = (value, message) => {if (!value) throw Error(message)};
try {
  const sidebar = document.getElementById('sidebar');
  const original = '<a class="sidebar-file" onclick="window.clicked=(window.clicked||0)+1">File</a><input value="original">';
  _replaceWorkspaceSidebarMarkup(sidebar, original, 'a');
  const template = _sidebarMarkupCache.get('a').template;
  sidebar.querySelector('a').classList.add('active');
  sidebar.querySelector('a').appendChild(document.createElement('span')).className='git-badge';
  sidebar.querySelector('input').value='edited';
  _replaceWorkspaceSidebarMarkup(sidebar, '<a>Different workspace</a>', 'b');
  _replaceWorkspaceSidebarMarkup(sidebar, original, 'a');
  assert(_sidebarMarkupCache.get('a').template === template, 'same markup reuses parsed template');
  assert(!sidebar.querySelector('.active,.git-badge'), 'live selection and decorations stay outside template');
  assert(sidebar.querySelector('input').value === 'original', 'live control state does not corrupt template');
  sidebar.querySelector('a').click();
  assert(window.clicked === 1, 'cloned inline file actions still run');
  const liveRow = sidebar.querySelector('a'), liveInput = sidebar.querySelector('input');
  liveRow.classList.add('git-modified');
  liveInput.value = 'in progress'; liveInput.focus();
  const changed = _replaceWorkspaceSidebarMarkup(sidebar, original, 'a', true);
  assert(changed === false && sidebar.querySelector('a') === liveRow, 'unchanged background refresh retains rows');
  assert(document.activeElement === liveInput && liveInput.value === 'in progress', 'unchanged refresh retains focus and control state');
  assert(liveRow.classList.contains('git-modified'), 'unchanged refresh retains live Git decorations');
  _replaceWorkspaceSidebarMarkup(sidebar, original, 'a');
  assert(sidebar.querySelector('a') !== liveRow, 'explicit navigation still clones pristine rows');
  const freshRow = sidebar.querySelector('a');
  _replaceWorkspaceSidebarMarkup(sidebar, original, 'b', true);
  assert(sidebar.querySelector('a') !== freshRow, 'scope changes replace rows even with identical markup');
  sidebar.innerHTML = '<a>Home view</a>';
  _replaceWorkspaceSidebarMarkup(sidebar, original, 'b', true);
  assert(sidebar.querySelector('input'), 'view replacement invalidates mounted markup');
  _replaceWorkspaceSidebarMarkup(sidebar, original, 'a', true);
  _replaceWorkspaceSidebarMarkup(sidebar, original+'<a>New file</a>', 'a', true);
  assert(sidebar.querySelectorAll('a').length === 2, 'changed files appear');
  assert(_sidebarMarkupCache.get('a').template !== template, 'changed markup replaces template');
  const row = (path, label=path) => `<a class="sidebar-file" data-filepath="${path}" onclick="window.clicked=(window.clicked||0)+1">${label}<button>History</button></a>`;
  const section = (id, children, height=22) => `<div id="${id}" class="sidebar-folder-children sidebar-recent-children open" style="contain-intrinsic-block-size:auto ${height}px">${children}</div>`;
  const firstTree = section('alpha', row('a.md')+row('b.md'),44) + section('beta', row('c.md'));
  _replaceWorkspaceSidebarMarkup(sidebar, firstTree, 'tree');
  const alpha = sidebar.querySelector('#alpha'), beta = sidebar.querySelector('#beta');
  const a = sidebar.querySelector('[data-filepath="a.md"]'), b = sidebar.querySelector('[data-filepath="b.md"]');
  a.classList.add('git-m'); a.appendChild(document.createElement('span')).className='git-badge';
  const button = a.querySelector('button'); button.focus();
  // Reorder whole sections, reorder retained files, rename one label, and add
  // a row. The caller still applies current Git status after changed markup.
  const secondTree = section('beta', row('c.md','Renamed label')) + section('alpha', row('b.md')+row('d.md')+row('a.md'),66);
  _replaceWorkspaceSidebarMarkup(sidebar, secondTree, 'tree', true);
  assert(sidebar.firstChild === beta && sidebar.lastChild === alpha, 'reordered containers retain identity');
  assert(sidebar.querySelector('[data-filepath="a.md"]') === a && sidebar.querySelector('[data-filepath="b.md"]') === b, 'unchanged file rows retain identity');
  assert(document.activeElement === button && a.querySelector('.git-badge'), 'retained focus and Git decoration survive section moves');
  assert(alpha.style.containIntrinsicBlockSize === 'auto 66px', 'changed intrinsic size applied');
  assert([...alpha.children].map(n=>n.dataset.filepath).join(',') === 'b.md,d.md,a.md', 'inserted and sorted file order correct');
  assert(beta.textContent.includes('Renamed label'), 'changed file label rendered');
  a.click(); assert(window.clicked === 2, 'retained handlers still run');
  // The fallback path also preserves a surviving focused control when the
  // browser lacks moveBefore, and a deletion removes only the obsolete row.
  Object.defineProperty(sidebar, 'moveBefore', {value:undefined,configurable:true});
  const thirdTree = section('alpha', row('a.md')) + section('beta', row('c.md','Renamed label'));
  _replaceWorkspaceSidebarMarkup(sidebar, thirdTree, 'tree', true);
  delete sidebar.moveBefore;
  assert(sidebar.firstChild === alpha && alpha.children.length === 1 && alpha.firstChild === a, 'deletion retains surviving rows');
  assert(document.activeElement === button, 'fallback move restores surviving focus');
  _replaceWorkspaceSidebarMarkup(sidebar, '<a>Another view</a>', 'other');
  _replaceWorkspaceSidebarMarkup(sidebar, thirdTree, 'tree');
  assert(!sidebar.querySelector('.git-m,.git-badge') && sidebar.querySelector('[data-filepath="a.md"]') !== a, 'incremental updates keep cached templates pristine');
  for(let step=0;step<30;step++) {
    const files=Array.from({length:9},(_,i)=>i).filter(i=>(i+step)%4!==0);
    if(step%2)files.reverse();
    const groups=['one','two','three'];if(step%3)groups.reverse();
    const markup=groups.map((id,index)=>section(id,files.filter(i=>i%3===index).map(i=>row(id+'/'+i+'.md', 'Label '+((i+step)%5))).join(''),files.filter(i=>i%3===index).length*22)).join('');
    _replaceWorkspaceSidebarMarkup(sidebar,markup,'varying',true);
    const expected=document.createElement('template');expected.innerHTML=markup;
    assert(sidebar.innerHTML===expected.innerHTML,'incremental DOM differs from a fresh render at step '+step);
    if(step===15) {
      // A different writer changed the middle of a container. The next
      // refresh must rebuild that container rather than mispairing its rows.
      sidebar.querySelector('.sidebar-folder-children').appendChild(document.createElement('em'));
    }
  }
  for (let i=0;i<10;i++) _replaceWorkspaceSidebarMarkup(sidebar, '<a>'+i+'</a>', 'scope-'+i);
  assert(_sidebarMarkupCache.size === 4, 'workspace count bounded');
  assert([..._sidebarMarkupCache.keys()].join(',') === 'scope-6,scope-7,scope-8,scope-9', 'oldest scopes evicted');
  const many = '<i></i>'.repeat(20000);
  for (let i=0;i<4;i++) _replaceWorkspaceSidebarMarkup(sidebar, many, 'large-'+i);
  assert(_sidebarMarkupCacheElements === 60000 && _sidebarMarkupCache.size === 3, 'aggregate elements bounded');
  _replaceWorkspaceSidebarMarkup(sidebar, '<i></i>'.repeat(60001), 'huge');
  assert(sidebar.children.length === 60001, 'oversized tree remains complete');
  assert(!_sidebarMarkupCache.has('huge') && _sidebarMarkupCacheElements === 60000, 'oversized tree not retained');
  _replaceWorkspaceSidebarMarkup(sidebar, '<a>Small again</a>', 'large-3');
  assert(_sidebarMarkupCacheElements === 40001, 'replacement releases previous template accounting');
  document.getElementById('result').textContent='PASS';
} catch(error) {document.getElementById('result').textContent='FAIL: '+error.stack;}
'''
    page = tmp_path / 'sidebar-cache.html'
    page.write_text('<!doctype html><meta charset="utf-8"><body><pre id="result">PENDING</pre>'
                    '<aside id="sidebar"></aside><script>' + helper + checks + '</script>')
    profile = tmp_path / 'chrome'
    process = subprocess.Popen([
        chrome, '--headless', '--no-sandbox', '--no-first-run', '--disable-background-networking',
        '--user-data-dir=' + str(profile), '--remote-debugging-port=0', 'about:blank',
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    try:
        deadline = time.monotonic() + 10
        while not (profile / 'DevToolsActivePort').exists():
            assert process.poll() is None and time.monotonic() < deadline, 'Chrome did not start'
            time.sleep(.05)
        rendered = tmp_path / 'rendered.html'
        result = subprocess.run([
            node, str(ROOT / 'scripts/chrome-dump-auth.mjs'), str(profile), page.as_uri(), str(rendered),
        ], capture_output=True, text=True, timeout=25, env={**os.environ, 'LAB_UI_AUTH_COOKIE': ''})
        assert result.returncode == 0, result.stderr
        match = re.search(r'<pre id="result">(.*?)</pre>', rendered.read_text(), re.S)
        assert match and match[1] == 'PASS', match[1] if match else 'No browser result'
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=5)
