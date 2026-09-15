"""Server views follow their workspace while same-view refreshes preserve state."""

import json

import pytest

from .test_frontend_terminal_ui import _js_between, _run_node


@pytest.mark.parametrize("mode", ["proxy", "direct"])
@pytest.mark.parametrize("other_vault", [False, True])
def test_same_named_servers_follow_workspace_switches(mode, other_vault):
    result = _run_node(
        "const mode = " + json.dumps(mode) + ";\n"
        "const otherVault = " + json.dumps(other_vault) + ";\n"
        + r"""
const assert = require('assert/strict');
const a = {name:'first', path:'/a/workspaces/first', vault:'a', is_workspace:true};
// Across vaults, even the workspace names may match.
const b = otherVault
  ? {...a, path:'/b/workspaces/first', vault:'b'}
  : {...a, name:'second', path:'/a/workspaces/second'};
let currentWorkspace = a, currentRepo = null, currentRepoInWorkspace = null;
let _workspaceDocPath = null, _workspaceDocEditing = false;
const server = (port, label) => ({name:'app', host:'127.0.0.1', port, label, mode, path:'/practice/'});
const _workspaceSidebarCache = new Map([
  [a.path, {proxies:[server(8003, 'First app')]}],
  [b.path, {proxies:[server(8011, 'Second app')]}],
]);
const _workspaceVaultId = workspace => workspace.vault;
const remembered = new Map();
const setLastWorkspaceDoc = (path, file) => remembered.set(path, file);
const renderRepoTabs = () => {}, _sidebarApplyForView = () => {};
const esc = value => String(value);
const escAttr = esc;
const CSS = {escape:value=>value};
const elements = {diffTabs:{style:{}}};
let paints = 0;
const content = {
  set innerHTML(html) {
    paints++;
    this.html = html;
    const wrap = html.match(/<div id="proxyWrap"[^>]*>/)[0];
    const dataset = {};
    for (const [,key,value] of wrap.matchAll(/data-([\w-]+)="([^"]*)"/g)) {
      dataset[key.replace(/-([a-z])/g, (_,letter)=>letter.toUpperCase())] = value;
    }
    elements.proxyWrap = {dataset};
    elements.proxyIframe = {src:html.match(/<iframe id="proxyIframe" src="([^"]*)"/)[1]};
  },
};
elements.content = content;
const document = {
  getElementById:id=>elements[id] || null,
  querySelectorAll:()=>[],
  body:{classList:{remove(){}}},
};
"""
        + _js_between("  function _proxyFromCachedSidebar(", "  function reloadWorkspaceProxy(")
        + r"""
(async()=>{
  for (const workspace of [a,b,a]) {
    currentWorkspace = workspace;
    _workspaceDocPath = remembered.get(workspace.path) || '__proxy__/app';
    const previousFrame = elements.proxyIframe;
    await openWorkspaceProxy('app');
    const frame = elements.proxyIframe;
    const port = workspace === a ? 8003 : 8011;
    const label = workspace === a ? 'First app' : 'Second app';
    assert.notEqual(frame, previousFrame, 'Switching workspaces must replace the previous app');
    assert.equal(frame.src, mode === 'direct'
      ? `http://127.0.0.1:${port}/practice/`
      : `/api/vault-proxy/${workspace.vault}/${workspace.name}/app/practice/`);
    assert(content.html.includes(label));
    assert(content.html.includes(`127.0.0.1:${port}`));
    assert.equal(remembered.get(workspace.path), '__proxy__/app');
    // Re-clicks and watcher refreshes must retain the live app's route/state.
    frame.route = '/lesson/42';
    await openWorkspaceProxy('app');
    assert.equal(elements.proxyIframe, frame);
    assert.equal(elements.proxyIframe.route, '/lesson/42');
  }
  assert.equal(paints, 3);
  console.log(JSON.stringify({passed:true}));
})().catch(error=>{console.error(error);process.exitCode=1;});
"""
    )
    assert result == {"passed": True}
