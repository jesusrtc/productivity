"""Workspace renaming keeps the original path and vault across navigation."""
from .test_frontend_terminal_ui import _js_between, _run_node


def test_rename_captures_target_and_updates_only_its_display_name():
    result = _run_node(r'''
const assert = require('assert/strict');
const a = {path:'/a/demo',name:'demo',display_name:'Alpha',vault:'a',is_workspace:true};
const b = {...a,path:'/b/demo',display_name:'Beta',vault:'b'};
let currentWorkspace = b, workspacesList = [a,b], workspaceTabsAll = [{...a},{...b}];
let vaultCatalog = [{id:'a',name:'Local',workspace_rows:[{...a}]},{id:'b',name:'SSD',workspace_rows:[{...b}]}];
let _vaultCurrent = vaultCatalog[1], _vaultCatalogInFlight = null;
const controls = {};
const control = id => controls[id] ||= {value:'',textContent:'',disabled:false,
  classList:{add(){},remove(){}},reset(){},focus(){},select(){},
  elements:{namedItem:()=>control('vaultWorkspaceName')}};
const document = {getElementById:control,querySelector:()=>control('heading'),title:'Beta'};
const window = {}, setTimeout = fn=>fn();
const _workspaceDisplayName = w=>w.display_name || w.name;
let renders = 0, requests = [], release;
const workspaceTabsRender = ()=>renders++;
const vaultRenderWorkspacesCard = async()=>{};
const fetch = (url,options)=>{requests.push({url,body:JSON.parse(options.body)});return new Promise(r=>release=r);};
''' + _js_between('  function _setWorkspaceDisplayName(', '  async function workspaceSaveDisplayName(')
        + _js_between('  let _vaultWorkspaceCreateBusy = false;', '  // "Workspaces" card:') + r'''
(async()=>{
  openVaultWorkspaceRenameModal(a,'a');
  assert.equal(control('vaultWorkspaceName').value,'Alpha');
  assert.equal(control('vaultWorkspaceContext').textContent,'Local');
  assert.equal(control('vaultWorkspaceTitle').textContent,'Rename workspace');
  control('vaultWorkspaceName').value='   ';
  await submitVaultWorkspace();
  assert.equal(requests.length,0);
  control('vaultWorkspaceName').value='  New Alpha  ';
  const saving = submitVaultWorkspace();
  await submitVaultWorkspace();
  assert.deepEqual(requests,[{url:'/api/workspaces/demo/field?vault=a',body:{field:'name',value:'New Alpha'}}]);
  release({ok:true,json:async()=>({id:'demo',name:'New Alpha'})});
  await saving;
  for (const row of [a,workspaceTabsAll[0],vaultCatalog[0].workspace_rows[0]]) {
    assert.equal(row.display_name,'New Alpha');
    assert.equal(row.name,'demo'); assert.equal(row.path,'/a/demo');
  }
  assert.equal(b.display_name,'Beta'); assert.equal(document.title,'Beta');
  assert.equal(currentWorkspace,b); assert.equal(_vaultCurrent.id,'b');
  assert.equal(renders,1);
  currentWorkspace = a;
  openVaultWorkspaceRenameModal(a,'a');
  control('vaultWorkspaceName').value='Final Alpha';
  const failed = submitVaultWorkspace();
  release({ok:false,json:async()=>({detail:'Cannot save'})}); await failed;
  assert.equal(control('vaultWorkspaceError').textContent,'Cannot save');
  assert.equal(a.display_name,'New Alpha');
  assert.equal(control('vaultWorkspaceSubmit').disabled,false);
  const retry = submitVaultWorkspace();
  release({ok:true,json:async()=>({name:'Final Alpha'})}); await retry;
  assert.equal(document.title,'Final Alpha');
  assert.equal(control('workspaceDisplayName').value,'Final Alpha');
  openVaultWorkspaceModal(vaultCatalog[1]);
  assert.equal(_vaultWorkspaceRenameTarget,null);
  assert.equal(control('vaultWorkspaceTitle').textContent,'New workspace');
  console.log(JSON.stringify({passed:true}));
})();
''')
    assert result['passed']
