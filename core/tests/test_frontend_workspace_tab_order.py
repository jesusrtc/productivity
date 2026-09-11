"""Workspace activation and polling preserve order; only a drop reorders tabs."""
from .test_frontend_terminal_ui import _js_between, _run_node


def test_workspace_order_survives_navigation_polling_drag_and_reload():
    result = _run_node(r'''
const assert = require('assert/strict');
const a = {path:'/a/workspaces/demo', name:'demo', vault:'a', tab_open:true, is_workspace:true};
const b = {...a, path:'/b/workspaces/demo', vault:'b'};
const c = {...a, path:'/a/workspaces/third', name:'third'};
const d = {...a, path:'/a/workspaces/new', name:'new', tab_open:false};
let repos = [a,b,c,d], workspaceTabsAll = [];
let workspaceTabsOrder = [], workspaceTabsOrderReady = false;
let workspaceTabsOrderLoad = null, workspaceTabsOrderSave = Promise.resolve(), workspaceTabsDragId = null;
let saved = ['third', b.path, a.path], reads = 0, writes = 0, paints = 0;
const fetch = async (url, options) => {
  assert.equal(url, '/api/ui/tab-order');
  if (options) {saved = JSON.parse(options.body).order; writes++;}
  else reads++;
  return {ok:true, json:async()=>saved};
};
const fetchRepos = async () => repos;
const vaultRefreshWorkspaceResources = () => {};
const classes = new Set(['workspace-active']);
let currentWorkspace = a;
const SELF_WORKSPACE_ID = '__self__', ASSISTANT_WORKSPACE_ID = '__assistant__', LAB_IS_ADMIN = true;
const tabBlocked = {}, _vaultForWorkspace = w => ({name:w.vault}), _workspaceDisplayName = w => w.name;
const workspaceTabsOpenIds = () => workspaceTabsAll.filter(w=>w.tab_open).map(w=>w.path);
function node(attrs) {
  const flags = new Set();
  return {
    attrs, events:{}, getAttribute:key=>attrs[key],
    addEventListener(type, fn) {this.events[type]=fn;},
    classList:{add:flag=>flags.add(flag), remove:(...names)=>names.forEach(n=>flags.delete(n))},
    getBoundingClientRect:()=>({left:0,width:100}),
  };
}
const el = {
  nodes:[], markup:'',
  set innerHTML(html) {
    paints++; this.markup=html;
    this.nodes = [...html.matchAll(/<div class="workspace-tab[^>]+>/g)].map(match=>
      node(Object.fromEntries([...match[0].matchAll(/([\w-]+)="([^"]*)"/g)].map(m=>[m[1],m[2]]))));
  },
  querySelectorAll(selector) {
    if (selector === '.workspace-tab') return this.nodes;
    if (selector === '.workspace-tab[data-kind="workspace"]') return this.nodes.filter(n=>n.attrs['data-kind']==='workspace');
    return [];
  },
};
const document = {getElementById:()=>el, body:{classList:{contains:key=>classes.has(key)}}};
const keys = () => el.nodes.map(n=>n.attrs['data-key']);
const expect = paths => assert.deepEqual(keys(), [SELF_WORKSPACE_ID, ASSISTANT_WORKSPACE_ID, ...paths]);
const tab = path => el.nodes.find(n=>n.attrs['data-key']===path);
const event = x => ({clientX:x, preventDefault(){}, dataTransfer:{setData(){}}});
''' + _js_between('  function workspaceTabsLoadOrder()', '  async function workspaceTabsClose(') + r'''
(async()=>{
  workspaceTabsRender(); assert.equal(paints,0); // Wait for saved order, avoiding a startup shuffle.
  await Promise.all([workspaceTabsRefresh(), workspaceTabsRefresh()]);
  assert.equal(reads,1);
  expect([c.path,b.path,a.path]); // Restore legacy unique names alongside cross-vault paths.
  for (const workspace of [b,c,a]) {
    currentWorkspace=workspace; workspaceTabsRender(); expect([c.path,b.path,a.path]);
  }
  classes.clear(); classes.add('self-active'); workspaceTabsRender(); expect([c.path,b.path,a.path]);
  repos=[d,b,a,c];
  await workspaceTabsRefresh(); expect([c.path,b.path,a.path]);
  const stablePaints=paints;
  await workspaceTabsRefresh(); assert.equal(paints,stablePaints);
  d.tab_open=true; currentWorkspace=d; classes.clear(); classes.add('workspace-active');
  workspaceTabsRender(); expect([c.path,b.path,a.path,d.path]);
  b.tab_open=false; workspaceTabsRender(); expect([c.path,a.path,d.path]);
  b.tab_open=true; workspaceTabsRender(); expect([c.path,b.path,a.path,d.path]);
  assert(!tab(SELF_WORKSPACE_ID).events.dragstart);
  assert.equal(tab(b.path).attrs.draggable,'true');
  const dragged=tab(b.path);
  dragged.events.dragstart(event(0));
  tab(a.path).events.dragover(event(90));
  await workspaceTabsRefresh(); assert.equal(tab(b.path),dragged);
  expect([c.path,b.path,a.path,d.path]);
  dragged.events.dragend(); expect([c.path,b.path,a.path,d.path]); // Cancel preserves order.
  dragged.events.dragstart(event(0));
  await tab(a.path).events.drop(event(90));
  expect([c.path,a.path,b.path,d.path]); // Same names in different vaults move independently.
  tab(d.path).events.dragstart(event(0));
  await tab(c.path).events.drop(event(10));
  expect([d.path,c.path,a.path,b.path]);
  currentWorkspace=b; workspaceTabsRender(); expect([d.path,c.path,a.path,b.path]);
  await workspaceTabsOrderSave;
  assert.deepEqual(saved,[d.path,c.path,a.path,b.path]);
  workspaceTabsOrder=[]; workspaceTabsOrderReady=false; workspaceTabsOrderLoad=null;
  await workspaceTabsRefresh(); expect([d.path,c.path,a.path,b.path]);
  assert.equal(reads,2);
  console.log(JSON.stringify({passed:true,writes}));
})();
''')
    assert result['passed']
    assert result['writes'] == 4  # Migration, new tab, and two explicit drops.
