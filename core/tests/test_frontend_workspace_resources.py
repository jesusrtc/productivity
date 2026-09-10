from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest


NODE = shutil.which("node")
ROOT = Path(__file__).resolve().parents[2]
LAB_APP = ROOT / "core/src/core/static/js/lab-app.js"
INDEX_HTML = ROOT / "core/src/core/templates/index.html"
LAB_SHELL_CSS = ROOT / "core/src/core/static/css/lab-shell.css"


def _run_node(script: str) -> dict:
    if NODE is None:
        pytest.skip("node is required for frontend terminal UI tests")
    proc = subprocess.run(
        [NODE, "-e", script],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    if proc.returncode != 0:
        raise AssertionError(f"node failed\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}")
    return json.loads(proc.stdout)


def _js_between(start_marker: str, end_marker: str) -> str:
    src = LAB_APP.read_text(encoding="utf-8")
    start = src.index(start_marker)
    end = src.index(end_marker, start)
    return src[start:end]




def test_workspace_close_preserves_sessions_and_stays_closed_after_poll():
    result = _run_node(r'''
const assert = require('assert/strict');
const requests = [];
const a = {path:'/a/workspaces/demo', name:'demo',vault:'a',tab_open:true};
const b = {...a,path:'/b/workspaces/demo',vault:'b'};
let currentWorkspace = a;
let workspaceTabsAll = [a,b], workspaceTabsHot = [{workspace_id:'demo',vault:'a'}];
const workspaceTabsSetOpen = async (path,open) => {requests.push(['open',path,open]);workspaceTabsAll.find(w=>w.path===path).tab_open=open;};
const workspaceTabsRefresh = async () => {requests.push(['refresh']);workspaceTabsRender();};
const goToVault = vault => {requests.push(['vault',vault]);currentWorkspace=null;};
const fetch = () => {throw Error('Closing must not kill resources');};
const confirm = () => {throw Error('Closing a tab needs no destructive confirmation');};
const el = {innerHTML:'',querySelectorAll:()=>[]};
const document = {getElementById:()=>el,body:{classList:{contains:()=>false}}};
const workspaceTabsOpenIds = () => workspaceTabsAll.filter(w=>w.tab_open).map(w=>w.path);
const workspaceTabsEsc = s=>s;
const _vaultForWorkspace = ()=>({color:'#abc',name:'Vault'});
const _workspaceDisplayName = w=>w.name;
const tabBlocked = {}, LAB_IS_ADMIN=false, SELF_WORKSPACE_ID='__self__';
''' + _js_between('  async function workspaceTabsClose(', '  function workspaceTabsTogglePicker(')
        + _js_between('  function workspaceTabsRender()', '  async function workspaceTabsReorder(') + r'''
(async()=>{
  await workspaceTabsClose({key:a.path,kind:'workspace',workspaceId:'demo',vault:'a'});
  assert.equal(a.tab_open,false);
  assert.equal(b.tab_open,true);
  assert(!el.innerHTML.includes('data-key="'+a.path+'"'));
  assert(el.innerHTML.includes('data-key="'+b.path+'"'));
  workspaceTabsRender();
  assert(!el.innerHTML.includes('data-key="'+a.path+'"'));
  console.log(JSON.stringify(requests));
})();
''')
    assert result == [['open', '/a/workspaces/demo', False], ['vault', 'a'], ['refresh']]


def test_resource_refresh_is_single_flight_and_ignores_old_vault_responses():
    result = _run_node(r'''
const assert = require('assert/strict');
const badge={textContent:'Loading',getAttribute:()=> 'same',classList:{toggle(){},remove(){}}};
const list={isConnected:true,querySelectorAll:()=>[badge]};
const document={getElementById:()=>list};
let _vaultCurrent={id:'a'}, calls=0, release;
const _vaultResourceRequests=new Set();
let fetch=()=>{calls++;return new Promise(resolve=>release=resolve);};
''' + _js_between('  function vaultWorkspaceResourceLabel(', '  async function vaultRenderWorkspacesCard()') + r'''
(async()=>{
  assert.equal(vaultWorkspaceResourceLabel({terminals:2,servers:1,kernels:1}), '2 terminals · 1 server · 1 kernel');
  assert.equal(vaultWorkspaceResourceLabel({}), 'No active resources');
  const first=vaultRefreshWorkspaceResources();
  await vaultRefreshWorkspaceResources();
  assert.equal(calls,1);
  _vaultCurrent={id:'b'};
  release({ok:true,json:async()=>({workspaces:{same:{terminals:9}}})});
  await first;
  assert.equal(badge.textContent,'Loading');
  fetch=async()=>({ok:true,json:async()=>({workspaces:{same:{terminals:3}}})});
  await vaultRefreshWorkspaceResources();
  assert.equal(badge.textContent,'3 terminals');
  fetch=async()=>({ok:false});
  await vaultRefreshWorkspaceResources();
  assert.equal(badge.textContent,'Resources unavailable');
  fetch=async()=>({ok:true,json:async()=>({workspaces:{}})});
  await vaultRefreshWorkspaceResources();
  assert.equal(badge.textContent,'No active resources');
  console.log(JSON.stringify({passed:true}));
})();
''')
    assert result == {'passed': True}
