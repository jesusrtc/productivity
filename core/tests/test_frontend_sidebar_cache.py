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


def test_sidebar_idle_layout_keeps_jobs_scoped_and_yields_between_groups():
    helper = _js_between('  const _sidebarLayoutJobs =',
                         '  // Re-renders just the workspace file sidebar')
    result = _run_node(r'''
const assert=require('node:assert/strict');
let number=0, currentSidebar=null;
const callbacks=new Map(), cancelled=[], listeners={}, bodyClasses=new Set();
let requestIdleCallback=(fn, options)=>{assert.equal(options.timeout,100);callbacks.set(++number,fn);return number};
const cancelIdleCallback=id=>{cancelled.push(id);callbacks.delete(id)};
const document={hidden:false,body:{classList:{contains:name=>bodyClasses.has(name)}},addEventListener:(type,fn)=>listeners[type]=fn,getElementById:()=>currentSidebar};
function group({closed=false,count=100}={}){
 return {closed,children:{length:count},ready:false,reads:0,
  closest(){return this.closed?{}:null},
  setAttribute(name,value){assert.equal(name,'data-sidebar-layout-ready');assert.equal(value,'');this.ready=true},
  removeAttribute(name){assert.equal(name,'data-sidebar-layout-ready');this.ready=false},
  getBoundingClientRect(){this.reads++;return {height:2200}}};
}
function sidebar(groups){
 const first={},last={};
 return {groups,isConnected:true,firstChild:first,lastChild:last,childNodes:[first,last],
  contains(g){return this.groups.includes(g)},querySelectorAll(selector){return this.groups.filter(g=>selector.includes(':not')?!g.ready:g.ready)}};
}
function tick(){const [id,fn]=callbacks.entries().next().value;callbacks.delete(id);fn()}
''' + helper + r'''
const a=group(),b=group(),closed=group({closed:true}),wide=group({count:201});
currentSidebar=sidebar([a,b,closed,wide]);
_primeSidebarLayout(currentSidebar);
assert.equal(a.reads,0,'scheduling must not synchronously lay out rows');
tick();assert.equal(a.reads,1);assert.equal(b.reads,0,'one group per callback');
tick();assert.equal(b.reads,1);
tick();tick();
assert.equal(closed.ready,false,'closed folders stay closed/unprepared');
assert.equal(wide.ready,false,'wide unbounded containers stay on normal layout');
assert.equal(_sidebarLayoutJobs.has(currentSidebar),false,'completed job is released');

const oldGroup=group(),newGroup=group();
currentSidebar=sidebar([oldGroup]);_primeSidebarLayout(currentSidebar);
const stale=callbacks.values().next().value,oldJob=_sidebarLayoutJobs.get(currentSidebar);
currentSidebar.groups=[newGroup];_primeSidebarLayout(currentSidebar);
assert.equal(oldJob.groups.length,0,'replacement releases old DOM references');
assert.equal(oldJob.first,null);assert.equal(oldJob.last,null);
stale();assert.equal(oldGroup.reads,0,'late cancelled callback cannot touch old rows');
assert.equal(_sidebarLayoutJobs.has(currentSidebar),true,'late callback cannot delete newer job');
tick();assert.equal(newGroup.reads,1);

const swapped=group();currentSidebar=sidebar([swapped]);_primeSidebarLayout(currentSidebar);
currentSidebar.firstChild={};tick();
assert.equal(swapped.reads,0,'another view replacing the sidebar invalidates the job');
assert.equal(_sidebarLayoutJobs.has(currentSidebar),false);

const detached=group();currentSidebar=sidebar([detached]);_primeSidebarLayout(currentSidebar);
currentSidebar.isConnected=false;tick();assert.equal(detached.reads,0);
assert.equal(_sidebarLayoutJobs.has(currentSidebar),false);

const hidden=group();currentSidebar=sidebar([hidden]);_primeSidebarLayout(currentSidebar);
document.hidden=true;tick();assert.equal(hidden.reads,0);
document.hidden=false;listeners.visibilitychange();tick();assert.equal(hidden.reads,1);

closed.closed=false;currentSidebar=sidebar([closed]);_primeSidebarLayout(currentSidebar);
tick();assert.equal(closed.reads,1,'newly opened group can be prepared');
const duringResize=group();currentSidebar=sidebar([closed,duringResize]);_primeSidebarLayout(currentSidebar);
_resetSidebarLayout(currentSidebar);
assert.equal(closed.ready,false,'width changes invalidate prepared geometry');
assert.equal(callbacks.size,0,'width changes cancel pending preparation');
bodyClasses.add('sidebar-resizing');_primeSidebarLayout(currentSidebar);
assert.equal(callbacks.size,0,'file refreshes during drag must not prepare offscreen groups');
bodyClasses.delete('sidebar-resizing');_primeSidebarLayout(currentSidebar);tick();tick();
assert.equal(closed.reads,2);assert.equal(duringResize.reads,1);
requestIdleCallback=undefined;
currentSidebar=sidebar([group()]);_primeSidebarLayout(currentSidebar);
assert.equal(callbacks.size,0,'unsupported browsers retain ordinary layout');
assert.equal(_sidebarLayoutJobs.has(currentSidebar),false);
console.log(JSON.stringify({ok:true,cancelled:cancelled.length}));
''')
    assert result == {'ok': True, 'cancelled': 2}


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
  assert(_replaceWorkspaceSidebarMarkup(sidebar, secondTree, 'tree', true), 'new/changed rows need cached decorations');
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
  assert(!_replaceWorkspaceSidebarMarkup(sidebar, thirdTree, 'tree', true), 'moves/deletions must not repaint already decorated rows');
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
  // Build balanced source ranges just as the folder renderers do. Nested
  // candidates let a changed parent reuse its unchanged descendants.
  const combine = items => {
    let html='', parts=[];
    for(const item of items) {
      parts.push(...item.parts.map(p=>({...p,start:p.start+html.length,end:p.end+html.length})));
      html+=item.html;
    }
    return {html,parts};
  };
  const leaf = html => ({html,parts:[]});
  const fragment = (id, content, extra='') => {
    const start=`<div class="sidebar-folder-children open" id="${id}"${extra}>`;
    const html=start+content.html+'</div>';
    return {html,parts:[{id,start:0,end:html.length},...content.parts.map(p=>({...p,start:p.start+start.length,end:p.end+start.length}))]};
  };
  const keep = fragment('keep',leaf(row('stable.md','KEEP UNCHANGED &amp; résumé')));
  const makeParts = step => combine([
    leaf('outside text\n'),
    fragment('outer',combine(step%2 ? [fragment('changed',leaf(row('updated.md','Revision '+step))),keep]
                                  : [keep,fragment('changed',leaf(row('updated.md','Revision '+step)))]),step%3?' data-state="yes"':''),
    leaf('<span>Trailing sibling '+step+'</span>'),
  ]);
  let input=makeParts(0);
  _replaceWorkspaceSidebarMarkup(sidebar,input.html,'parts',false,input.parts);
  const stable=sidebar.querySelector('[data-filepath="stable.md"]');
  stable.classList.add('git-m'); stable.querySelector('button').focus();
  const pristine=_sidebarMarkupCache.get('parts').template;
  for(let step=1;step<=30;step++) {
    input=makeParts(step);
    const parsed=[];
    const innerHTML=Object.getOwnPropertyDescriptor(Element.prototype,'innerHTML');
    Object.defineProperty(Element.prototype,'innerHTML',{...innerHTML,set(value){if(this.tagName==='TEMPLATE')parsed.push(String(value));innerHTML.set.call(this,value)}});
    try {_replaceWorkspaceSidebarMarkup(sidebar,input.html,'parts',true,input.parts);}
    finally {Object.defineProperty(Element.prototype,'innerHTML',innerHTML);}
    assert(parsed.length===1&&!parsed[0].includes('KEEP UNCHANGED'), 'unchanged descendant reparsed at step '+step);
    assert(sidebar.querySelector('[data-filepath="stable.md"]')===stable, 'reused template must retain unchanged live rows');
    assert(stable.classList.contains('git-m')&&document.activeElement===stable.querySelector('button'),'fragment reuse lost live decoration/focus');
    const expected=document.createElement('template');expected.innerHTML=input.html;
    const cached=_sidebarMarkupCache.get('parts');
    assert(cached.template.innerHTML===expected.innerHTML,'fragment assembly differs from full parse at step '+step);
    assert([...cached.parts.values()].every(p=>cached.template.content.contains(p.node)),'fragment index retained nodes from another template');
    assert(!cached.template.content.querySelector('[data-sidebar-part],.git-m'),'placeholders or live decorations leaked into template');
  }
  assert(pristine.content.querySelector('#keep'),'cloning fragments must not consume older pristine templates');
  _replaceWorkspaceSidebarMarkup(sidebar,input.html,'parts',false,input.parts);
  const expectedParts=document.createElement('template');expectedParts.innerHTML=input.html;
  assert(sidebar.innerHTML===expectedParts.innerHTML,'explicit navigation using assembled template differs from full parse');
  // Literal application content cannot be mistaken for an internal placeholder.
  const literal=combine([keep,leaf('<template DATA-SIDEBAR-PART="0"><i>Literal template</i></template>')]);
  _replaceWorkspaceSidebarMarkup(sidebar,literal.html,'parts',true,literal.parts);
  expectedParts.innerHTML=literal.html;
  assert(_sidebarMarkupCache.get('parts').template.innerHTML===expectedParts.innerHTML,'literal template was consumed as a reuse marker');
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
