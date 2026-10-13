"""Cold server restores and pop-outs keep the configured URL and clicking browser."""

import json

import pytest

from .test_frontend_terminal_ui import ROOT, _js_between, _run_node


CONTEXT = r"""
const assert = require('assert/strict');
const workspace = {is_workspace:true, name:'vm', path:'/local/projects/vm', vault:'local'};
let currentWorkspace = workspace, currentRepo = null, currentRepoInWorkspace = null;
let _workspaceDocPath = null, _workspaceDocEditing = false;
const _workspaceSidebarCache = new Map();
const _workspaceVaultId = w => w.vault;
const setLastWorkspaceDoc = () => {}, renderRepoTabs = () => {}, _sidebarApplyForView = () => {};
const esc = String, escAttr = String, CSS = {escape:String};
const elements = {diffTabs:{style:{}}};
const content = {html:'', set innerHTML(value) {
  this.html = value;
  const wrap = value.match(/<div id="proxyWrap"[^>]*>/)?.[0];
  delete elements.proxyWrap; delete elements.proxyIframe;
  if (!wrap) return;
  const dataset = {};
  for (const [,key,text] of wrap.matchAll(/data-([\w-]+)="([^"]*)"/g))
    dataset[key.replace(/-([a-z])/g, (_,letter)=>letter.toUpperCase())] = text;
  elements.proxyWrap = {dataset};
  elements.proxyIframe = {src:value.match(/<iframe id="proxyIframe" src="([^"]*)"/)[1]};
}};
elements.content = content;
const document = {baseURI:'http://lab.example/', body:{classList:{remove(){}}},
  getElementById:id=>elements[id], querySelectorAll:()=>[], addEventListener(){}};
"""


@pytest.mark.parametrize("mode", ["direct", "proxy"])
@pytest.mark.parametrize("outcome", ["success", "failed", "missing", "navigated"])
def test_restored_server_reads_saved_entry_without_sidebar(mode, outcome):
    result = _run_node(
        CONTEXT
        + "const mode=" + json.dumps(mode) + ", outcome=" + json.dumps(outcome) + ";\n"
        + r"""
const requests = [];
let release;
const fetch = url => { requests.push(url); return new Promise(resolve=>{release=resolve;}); };
"""
        + _js_between("  function _proxyFromCachedSidebar(", "  function reloadWorkspaceProxy(")
        + r"""
(async()=>{
  const pending = openWorkspaceProxy('ubuntu-novnc');
  assert.equal(elements.proxyIframe, undefined, 'no guessed root before config loads');
  assert.deepEqual(requests, ['/api/server-config?workspace_id=vm&vault=local']);
  if (outcome==='navigated') {
    currentWorkspace = {...workspace, path:'/other/projects/vm', vault:'other'};
    content.html = 'Other workspace';
  }
  release({ok:outcome!=='failed', json:async()=>({servers:outcome==='missing'?[]:[{
    name:'ubuntu-novnc', host:'127.0.0.1', port:6080, path:'/lab.html?resize=scale', mode,
    label:'Ubuntu desktop',
  }]})});
  await pending;
  if (outcome==='success') {
    const expected = mode==='direct' ? 'http://127.0.0.1:6080/lab.html?resize=scale'
      : '/api/vault-proxy/local/vm/ubuntu-novnc/lab.html?resize=scale';
    assert.equal(elements.proxyIframe.src, expected);
    assert.equal(elements.proxyWrap.dataset.proxyUrl, expected);
    assert(content.html.includes('Ubuntu desktop') && content.html.includes('6080'));
  } else {
    assert.equal(elements.proxyIframe, undefined);
    assert.equal(elements.proxyWrap, undefined);
    if (outcome==='navigated') assert.equal(content.html, 'Other workspace');
    else assert(content.html.includes(outcome==='missing'?'not configured':'Could not load'));
  }
  console.log(JSON.stringify({passed:true}));
})().catch(error=>{console.error(error);process.exitCode=1;});
"""
    )
    assert result == {"passed": True}


@pytest.mark.parametrize("mode", ["direct", "proxy"])
def test_popout_opens_synchronously_in_clicking_browser_with_or_without_sidebar(mode):
    result = _run_node(
        CONTEXT + "const mode=" + json.dumps(mode) + ";\n"
        + r"""
window.LAB_EXTERNAL_BROWSER = true;
window.location = new URL(document.baseURI);
const opened = [], nativeCalls = [];
window.open = (...args)=>{opened.push(args);return null;};
const fetch = (...args)=>{nativeCalls.push(args);throw Error('Must not open on server desktop');};
"""
        + (ROOT / "core/src/core/static/js/lib/external-links.js").read_text()
        + "\nconst LabExternalLinks=window.LabExternalLinks;\n"
        + _js_between("  function _proxyFromCachedSidebar(", "  // Inline iframe + controls bar.")
        + _js_between("  function openWorkspaceProxyTab(", "  function _workspaceProxyAppName(")
        + r"""
const entry = {name:'ubuntu-novnc', host:'127.0.0.1', port:6080,
  path:'/lab.html?resize=scale', mode};
_workspaceSidebarCache.set(workspace.path, {proxies:[entry]});
const expected = mode==='direct' ? 'http://127.0.0.1:6080/lab.html?resize=scale'
  : 'http://lab.example/api/vault-proxy/local/vm/ubuntu-novnc/lab.html?resize=scale';
openWorkspaceProxyTab(entry.name);
assert.equal(opened.length, 1, 'opening happens in the click, without await');
assert.equal(opened[0][0], expected);
assert.equal(opened[0][1], '_blank');
assert(opened[0][2].includes('noopener'));
assert.equal(nativeCalls.length, 0, 'local-server browser routing must not be used');
_workspaceSidebarCache.clear();
elements.proxyWrap = {dataset:{proxy:entry.name, workspacePath:workspace.path, proxyUrl:expected}};
openWorkspaceProxyTab(entry.name);
assert.equal(opened[1][0], expected, 'rendered entry survives sidebar cache eviction');
currentWorkspace = {...workspace, path:'/other/projects/vm', vault:'other'};
openWorkspaceProxyTab(entry.name);
assert.equal(opened.length, 2, 'never use another workspace view');
delete elements.proxyWrap;
openWorkspaceProxyTab(entry.name);
assert.equal(opened.length, 2, 'never guess the upstream root without a saved entry');
console.log(JSON.stringify({passed:true}));
"""
    )
    assert result == {"passed": True}
