"""Workspace renaming moves paths while preserving terminal identity."""
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
  assert.deepEqual(requests,[{url:'/api/workspaces/demo/rename?vault=a',body:{name:'New Alpha'}}]);
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


def test_folder_move_preserves_terminal_connections_and_migrates_path_state():
    result = _run_node(r'''
const assert = require('assert/strict');
const old='/a/workspaces/demo', next='/a/workspaces/new-name';
let currentWorkspace={path:old,name:'demo',is_workspace:true};
const workspacesList=[currentWorkspace,{path:'/b/workspaces/demo',name:'demo'}];
let workspaceTabsAll=[{...currentWorkspace}], vaultCatalog=[{workspace_rows:[{...currentWorkspace}]}];
let _vaultCurrent=vaultCatalog[0],workspaceTabsOrder=[old,'/b/workspaces/demo'];
let _workspaceDocRoot=old+'/repo', _workspaceDeleteTarget={path:old};
let _sidebarFileConfigScope=encodeURIComponent(old),_sidebarFileConfig={folderScopes:[{path:old+'/repo'}]};
let termSessions=[{name:'neurona-uuid',session_id:'uuid',workspace_id:'demo',linked_scope:{root:old+'/repo'}}];
const sessionSocket={readyState:1};
const _termCache=new Map([['demo::neurona-uuid',{ws:sessionSocket}]]);
const _termSessionsCache=new Map([['a::demo',termSessions]]);
const _workspaceSidebarCache=new Map([[old,{}]]),_workspaceAttrsCache=new Map([[old,{}]]);
const _workspaceDocCache=new Map([[old+'::notes/a.md',{}]]),_gitStatusByPath=new Map([[old,{}]]);
const localStorage={['labWorkspaceLastUsed:'+old]:'123',
  ['labSidebar:'+encodeURIComponent(old)]:JSON.stringify({root:old,other:old+'-other'}),
  getItem(k){return this[k];},setItem(k,v){this[k]=v;},removeItem(k){delete this[k];}};
const window={location:{href:'http://example.test/?workspace='+encodeURIComponent(old)}};
let newUrl,rendered=0,sidebar=0;
const history={state:null,replaceState(s,t,u){newUrl=u;}};
const termRenderSessionList=()=>rendered++,_refreshWorkspaceSidebar=()=>sidebar++;
''' + _js_between('  function _applyWorkspaceLocation(', '  async function workspaceSaveDisplayName(') + r'''
_applyWorkspaceLocation(old,next);
assert.equal(currentWorkspace.path,next); assert.equal(currentWorkspace.name,'demo');
assert.equal(workspacesList[1].path,'/b/workspaces/demo');
assert.equal(termSessions[0].name,'neurona-uuid'); assert.equal(termSessions[0].session_id,'uuid');
assert.equal(termSessions[0].linked_scope.root,next+'/repo');
assert.equal(_termCache.get('demo::neurona-uuid').ws,sessionSocket);
assert.deepEqual(workspaceTabsOrder,[next,'/b/workspaces/demo']);
assert.equal(newUrl.searchParams.get('workspace'),next);
assert.equal(localStorage['labWorkspaceLastUsed:'+next],'123');
assert.deepEqual(JSON.parse(localStorage['labSidebar:'+encodeURIComponent(next)]),{root:next,other:old+'-other'});
assert.equal(_workspaceDocCache.size,0);
assert.equal(_sidebarFileConfigScope,encodeURIComponent(next));
assert.equal(rendered,1);assert.equal(sidebar,1);
console.log(JSON.stringify({passed:true}));
''')
    assert result['passed']
