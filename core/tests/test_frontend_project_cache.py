from pathlib import Path
import shutil
import subprocess

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
