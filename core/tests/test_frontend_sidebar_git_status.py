"""Git decoration indexes preserve prefix semantics and live DOM behavior."""
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import time

import pytest

from .test_frontend_terminal_ui import ROOT, _js_between, _run_node


def test_git_index_matches_original_scans():
    helper = _js_between('  function _sidebarGitStatusIndex(', '  function _sidebarGitRows(')
    result = _run_node(helper + r'''
const assert = require('node:assert/strict');
let checked=0;
function check(files, ignored, paths) {
  const index=_sidebarGitStatusIndex(files,ignored), keys=Object.keys(files);
  for(const p of paths) {
    let status=files[p] || '';
    if(!status) for(const k of keys) {
      if((files[k]==='U'||files[k]==='A') && p.startsWith(k+'/')) {status=files[k];break;}
    }
    const isIgnored=ignored.some(prefix=>{
      const base=prefix.replace(/\/+$/,'');
      return base && (p===base || p.startsWith(base+'/'));
    });
    let modified=false,any=false;
    for(const k of keys) if(k.startsWith(p+'/')) {
      any=true;
      if(['M','D','R'].includes(files[k])) {modified=true;break;}
    }
    assert.equal(index.statusFor(p),status,'status '+JSON.stringify(p));
    assert.equal(index.isIgnored(p),isIgnored,'ignored '+JSON.stringify(p));
    assert.equal(index.folderStatus(p),modified?'M':any?'U':'','folder '+JSON.stringify(p));
    checked++;
  }
}
const paths=['','/','//','a','ab','a/b','a/b/','a/b/c','a//b','a///b/c',
  'a/deleted','a/renamed','a/unknown','a/falsy','a2/x','tmp','tmp/x','tmp2/x',
  '空 白/"quoted"/x','1','1/x','10/x','constructor','toString'];
const entries=[['a/b','U'],['a','A'],['a/b/c','M'],['a/deleted','D'],['a/renamed','R'],
  ['a/unknown','?'],['a/falsy',''],['','A'],['a/','U'],['a2','M'],['1','A'],['10','U'],
  ['空 白/"quoted"','A']];
const ignored=['tmp///','a/','a//b/','空 白/','', '///'];
check(Object.fromEntries(entries),ignored,paths);
check(Object.fromEntries(entries.reverse()),ignored,paths);
check({},[],paths);
check(Object.create(null),['///'],paths);
// Deterministic varied trees include redundant slashes, unknown/falsy
// statuses and overlapping roots. Compare observable behavior, not internals.
let seed=817,random=n=>{seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed%n};
const parts=['a','b','a2','1','空 白','','quote"'];
const path=()=>Array.from({length:1+random(5)},()=>parts[random(parts.length)]).join('/');
const states=['A','U','M','D','R','?', '',null];
for(let trial=0;trial<100;trial++) {
  const files={},ignored=[],queries=[...paths];
  for(let i=0;i<80;i++) {const p=path();files[p]=states[random(states.length)];queries.push(p,p+'/child');}
  for(let i=0;i<15;i++) ignored.push(path()+'/'.repeat(random(4)));
  for(let i=0;i<100;i++) queries.push(path());
  check(files,ignored,queries);
}
console.log(JSON.stringify({checked}));
''')
    assert result['checked'] > 28000


def test_git_decorations_in_chrome(tmp_path):
    chrome = (os.environ.get('CHROME_BIN') or shutil.which('chromium')
              or '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
    node = shutil.which('node')
    if not Path(chrome).is_file() or not node:
        pytest.skip('Chrome and Node required')
    helper = _js_between('  const _GIT_ROW_CLASSES =', '  // Rebuilt rows need cached decorations')
    checks = r'''
const currentWorkspace={path:'/active'}, _sidebarScopedRoot=()=>'/checkout';
const assert=(value,message)=>{if(!value)throw Error(message)};
try {
  const sidebar=document.getElementById('sidebar');
  const file=(id,path,extra='',actions=true)=>`<a id="${id}" tabindex="0" class="sidebar-file active" data-filepath="${path}" ${extra}><span>File</span>${actions?'<button class="sidebar-actions">History</button>':''}</a>`;
  const folder=(id,path,scope='workspace:alpha')=>`<div id="${id}" class="sidebar-folder" data-tree-scope="${scope}" data-tree-path="${path}">Folder</div>`;
  const rows=file('modified','src/a.md')+file('added','new/a.md')+file('untracked','loose/a.md','',false)
    +file('deleted','src/d.md')+file('renamed','src/r.md')+file('ignored','cache/a.md')+file('clean','src/clean.md')
    +file('foreign','src/a.md','data-entry-root="/other"')+file('proxy','__proxy__/x')
    +folder('src','src')+folder('new','new')+folder('loose','loose')+folder('cache','cache')
    +folder('meta','src','meta:shared')+folder('recent','src','recent:alpha');
  sidebar.innerHTML=rows;
  const get=id=>document.getElementById(id);
  const entry={files:{'src/a.md':'M','new':'A','loose':'U','src/d.md':'D','src/r.md':'R'},ignored:['cache///']};
  get('modified').querySelector('button').focus();const focus=document.activeElement;
  _sidebarApplyGitStatus(entry);
  for(const [id,status,title] of [['modified','M','Modified'],['added','A','Added'],['untracked','U','Untracked'],['deleted','D','Deleted'],['renamed','R','Renamed']]) {
    const row=get(id),badge=row.querySelector('.git-badge');
    assert(row.classList.contains('git-'+status.toLowerCase()) && row.classList.contains('active'),id+' class');
    assert(badge?.textContent===status && badge.title===title,id+' badge');
    assert(id==='untracked'?row.lastChild===badge:badge.nextSibling===row.querySelector('button'),id+' history position');
  }
  assert(get('ignored').classList.contains('git-ignored') && !get('ignored').querySelector('.git-badge'),'ignored file');
  for(const id of ['clean','foreign','proxy','meta','recent'])assert(!get(id).querySelector('.git-badge,.git-dot') && !get(id).className.includes('git-'),id+' remains plain');
  for(const [id,cls] of [['src','git-m'],['new','git-a'],['loose','git-u']])assert(get(id).classList.contains(cls) && get(id).querySelector('.git-dot')?.title==='Contains changes',id+' rollup');
  assert(get('cache').classList.contains('git-ignored') && !get('cache').querySelector('.git-dot'),'ignored folder');
  const observer=new MutationObserver(()=>{});observer.observe(sidebar,{subtree:true,childList:true,attributes:true,characterData:true});
  _sidebarApplyGitStatus(entry);
  assert(observer.takeRecords().length===0,'unchanged status must cause zero DOM mutations');
  assert(document.activeElement===focus,'unchanged Git repaint keeps focus');
  _sidebarApplyGitStatus({files:{'src/a.md':'R'},ignored:[]});
  assert(get('modified').classList.contains('git-r') && !get('modified').classList.contains('git-m'),'changed status class');
  assert(get('modified').querySelector('.git-badge').textContent==='R' && get('modified').querySelector('.git-badge').title==='Renamed','changed badge');
  assert(!get('added').querySelector('.git-badge') && !get('ignored').classList.contains('git-ignored'),'stale decorations removed');
  // Clearing also finds orphan badges/dots, and continues to respect scope.
  get('clean').appendChild(document.createElement('span')).className='git-badge';
  get('cache').appendChild(document.createElement('span')).className='git-dot';
  for(const id of ['foreign','proxy']) {get(id).classList.add('git-m');get(id).appendChild(document.createElement('span')).className='git-badge';}
  get('meta').classList.add('git-m');get('meta').appendChild(document.createElement('span')).className='git-dot';
  _sidebarApplyGitStatus({files:{},ignored:[]});
  for(const id of ['modified','clean','cache','src'])assert(!get(id).className.includes('git-') && !get(id).querySelector('.git-badge,.git-dot'),id+' cleared');
  for(const id of ['foreign','proxy','meta'])assert(get(id).classList.contains('git-m') && get(id).querySelector('.git-badge,.git-dot'),id+' scope preserved');
  observer.takeRecords();_sidebarApplyGitStatus(null);
  assert(observer.takeRecords().length===0,'repeated clean status is mutation-free');
  const pristine=document.createElement('template');pristine.innerHTML=rows;
  sidebar.replaceChildren(pristine.content.cloneNode(true));_sidebarApplyGitStatus(entry);
  assert(get('modified').querySelector('.git-badge')?.textContent==='M' && !pristine.content.querySelector('.git-badge'),'fresh clones get status without contaminating templates');
  // Exercise a real large DOM and duplicate recent shortcuts.
  const files={};sidebar.innerHTML=Array.from({length:5000},(_,i)=>{
    if(i<2500)files['notes/'+i]='M';
    return file('tree-'+i,'notes/'+i)+file('recent-'+i,'notes/'+i);
  }).join('');
  _sidebarApplyGitStatus({files});
  assert(sidebar.querySelectorAll('.git-badge').length===5000,'large tree and recent shortcut counts');
  observer.takeRecords();_sidebarApplyGitStatus({files});
  assert(observer.takeRecords().length===0,'large repeated update is mutation-free');
  _sidebarApplyGitStatus({});
  assert(!sidebar.querySelector('.git-badge,.git-m'),'large clean result removes every badge');
  observer.disconnect();document.getElementById('result').textContent='PASS';
} catch(error) {document.getElementById('result').textContent='FAIL: '+error.stack;}
'''
    page = tmp_path / 'sidebar-git.html'
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
