import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_workspace_delete_mode_requires_context_action_and_confirmation():
    node = shutil.which('node')
    if not node:
        pytest.skip('node is required')
    script = r'''
const fs = require('fs'), vm = require('vm'), assert = require('assert/strict');
const source = fs.readFileSync('core/src/core/static/js/lab-app.js', 'utf8');
const between = (start, end) => { const i = source.indexOf(start); assert(i >= 0); return source.slice(i, source.indexOf(end, i)); };
const elements = new Map();
function element() {
  const makeButton = () => ({handlers: {}, addEventListener(k,f) {this.handlers[k]=f;}, focus() {}});
  const button = makeButton(), rename = makeButton();
  return {style:{}, handlers:{}, button, rename, offsetWidth:200, offsetHeight:40,
    setAttribute(){}, addEventListener(k,f) {this.handlers[k]=f;}, querySelector(s){return s.includes('delete') ? button : rename;},
    remove(){elements.delete(this.id);}, contains(){return false;}};
}
const a = {path:'/a/workspaces/same',name:'same',display_name:'Alpha',vault:'a',is_workspace:true};
const b = {...a,path:'/b/workspaces/same',vault:'b'};
const target = {path:a.path,id:'same',name:'Alpha',vault:'a'};
let requests = [], confirmation = false, prompts = [], deletedToast = [], navigated = [];
const context = vm.createContext({
  document:{getElementById:id => elements.get(id), createElement:element, addEventListener(){},
    body:{appendChild(el){elements.set(el.id,el);},classList:{remove(){}}}},
  window:{innerWidth:1200,innerHeight:900,addEventListener(){}},
  currentWorkspace:null, currentRepo:null,currentRepoInWorkspace:null,
  _workspaceDeleteTarget:null,_workspaceDeleteBusy:false,
  _workspaceVaultId:w => w.vault, _workspaceDisplayName:w => w.display_name || w.name,
  workspacesList:[a,b],workspaceTabsAll:[a,b],workspaceTabsHot:[],
  selectRepo(path){context.currentWorkspace=context.workspacesList.find(w=>w.path===path);},
  renderRepoTabs(){}, confirm(text){prompts.push(text);return confirmation;},
  fetch:async (url,options) => {requests.push({url,options});return {ok:true,json:async()=>({killed:[]})};},
  _termSessionsCache:new Map(),_workspaceSidebarCache:new Map(),_workspaceAttrsCache:new Map(),
  _termSessionsKey:(id,vault)=>vault+':'+id,localStorage:{removeItem(){}},
  goToVault(vault){navigated.push(vault);context._workspaceDeleteTarget=null;},
  workspaceTabsRefresh:async()=>{},explorerToast:(message,error)=>deletedToast.push({message,error}),
  openVaultWorkspaceRenameModal(workspace,vault){assert.equal(workspace,a);assert.equal(vault,'a');},
});
vm.runInContext(between('  function _workspaceDeleteIsVisible()', '  async function vaultRenderWorkspacesCard()'), context);
vm.runInContext(between('  function _swapViewState(', '  // Navigate to a real workspace'), context);
vm.runInContext(between('  function goToWorkspace(path', '  // Navigate to a workspace by its id'), context);
(async()=>{
  context.goToWorkspace(a.path,{replace:true});
  assert.equal(context._workspaceDeleteIsVisible(),false);
  await context.deleteCurrentWorkspace();
  assert.equal(prompts.length,0);
  let prevented=false;
  context.openVaultWorkspaceMenu({preventDefault(){prevented=true;},stopPropagation(){},clientX:300,clientY:200,
    currentTarget:{getBoundingClientRect:()=>({left:1,bottom:20}),focus(){}}},a,'a');
  const menu=elements.get('vaultWorkspaceMenu');
  assert(prevented && menu.innerHTML.includes('class="danger"') && menu.innerHTML.includes('Delete workspace'));
  assert(menu.innerHTML.includes('Rename workspace'));
  menu.rename.handlers.click();
  assert.equal(requests.length,0);
  const navigate=context.goToWorkspace;
  context.goToWorkspace=(path,opts)=>navigate(path,{...opts,replace:true});
  menu.button.handlers.click();
  assert.equal(context._workspaceDeleteIsVisible(),true);
  assert.equal(context.currentWorkspace.path,a.path);
  assert.equal(requests.length,0);
  await context.deleteCurrentWorkspace();
  assert.equal(requests.length,0); // Cancel never sends a mutation.
  assert(prompts[0].includes(a.path) && prompts[0].includes('permanently lost') && prompts[0].includes('cannot be undone'));
  context.goToWorkspace(b.path,{replace:true});
  assert.equal(context._workspaceDeleteIsVisible(),false);
  context.goToWorkspace(a.path,{replace:true});
  assert.equal(context._workspaceDeleteIsVisible(),false); // Returning normally stays unarmed.
  context.goToWorkspace(a.path,{replace:true,deleteTarget:target});
  context.currentWorkspace=b;
  assert.equal(context._workspaceDeleteIsVisible(),false); // Same ID, different vault.
  context.currentWorkspace=a;
  confirmation=true;
  context.fetch=async()=>({ok:false,json:async()=>({detail:'stop failed'})});
  await context.deleteCurrentWorkspace();
  assert.equal(context._workspaceDeleteBusy,false);
  assert.equal(context._workspaceDeleteIsVisible(),true);
  assert(deletedToast.at(-1).error);
  let release;
  context.fetch=(url,options)=>{requests.push({url,options});return new Promise(resolve=>release=resolve);};
  const pending=context.deleteCurrentWorkspace();
  await context.deleteCurrentWorkspace();
  assert.equal(requests.length,1); // Duplicate clicks cannot send duplicate deletes.
  release({ok:true,json:async()=>({killed:[]})});
  await pending;
  assert.equal(requests[0].url,'/api/workspaces/same?vault=a');
  assert.equal(requests[0].options.method,'DELETE');
  assert.deepEqual(JSON.parse(requests[0].options.body),{path:a.path,confirmed:true});
  assert.deepEqual(navigated,['a']);
  assert.equal(context.workspaceTabsAll.length,1);
  assert.equal(context.workspaceTabsAll[0].path,b.path);
  assert.equal(context._workspaceDeleteIsVisible(),false);
  assert.equal(context._workspaceDeleteBusy,false);
  const render=between('  function renderRepoTabs()', '  function showScopedCodeSearch()');
  assert(render.indexOf('class="repo-tab focus-toggle"') < render.indexOf('if (_workspaceDeleteIsVisible())'));
  assert(render.includes('DELETE WORKSPACE'));
  assert(source.includes("row.addEventListener('contextmenu', event => openVaultWorkspaceMenu(event, workspace, vault.id))"));
  assert(source.includes('let _workspaceDeleteTarget = null;')); // Reload starts unarmed.
  console.log('delete navigation, cancellation, exact target, failure and duplicate-click checks passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
'''
    result = subprocess.run([node, '-e', script], cwd=ROOT, text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr
