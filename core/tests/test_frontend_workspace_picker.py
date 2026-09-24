"""The new-tab picker routes workspaces and creation to their owning vault."""
import pytest

from .test_frontend_terminal_ui import _js_between, _run_node


def test_picker_selects_vault_and_opens_existing_or_new_workspace():
    result = _run_node(r'''
const assert = require('assert/strict');
const a = {id:'a', name:'Local', color:'#123456', workspace_rows:[{name:'demo', path:'/a/demo', is_workspace:true}]};
const b = {id:'b', name:'SSD', color:'#abcdef', workspace_rows:[{name:'demo', path:'/b/demo', is_workspace:true}]};
const vaultCatalog = [a,b,{id:'offline',unavailable:true}];
const currentWorkspace = {vault:'a'}, currentVaultId = 'a', LAB_IS_ADMIN = true;
const _workspaceVaultId = w => w.vault, _workspaceDisplayName = w => w.name;
const workspaceTabsOpenIds = () => ['/a/demo'];
const workspaceTabsEsc = s => String(s);
let opened, created, closed = 0;
const goToWorkspace = path => opened = path;
const openVaultWorkspaceModal = vault => created = vault;
const workspaceTabsClosePicker = () => closed++;
const controls = {};
const control = key => controls[key] ||= {addEventListener(type, fn){this[type]=fn;},focus(){}};
const picker = {
  innerHTML:'', querySelector:control,
  querySelectorAll:selector => {
    const attr = selector.slice(1,-1);
    return [...picker.innerHTML.matchAll(new RegExp(attr + '="([^"]+)"', 'g'))].map(m => {
      const row = control(m[1]); row.getAttribute = () => m[1]; return row;
    });
  },
};
const document = {getElementById:()=>picker};
''' + _js_between('  function workspaceTabsRenderPicker(', '  function workspaceTabsStartPolling()') + r'''
workspaceTabsRenderPicker();
assert(picker.innerHTML.includes('/a/demo'));
assert(picker.innerHTML.includes('/b/demo'));
assert(picker.innerHTML.includes('All vaults'));
assert(picker.innerHTML.includes('--vault-color:#123456'));
assert(picker.innerHTML.includes('--vault-color:#abcdef'));
assert(picker.innerHTML.indexOf('aria-label="Local"') < picker.innerHTML.indexOf('/a/demo'));
assert(picker.innerHTML.indexOf('aria-label="SSD"') < picker.innerHTML.indexOf('/b/demo'));
assert(!picker.innerHTML.includes('Open vault'));
controls['[data-action="create"]'].click();
assert(picker.innerHTML.includes('Choose a vault'));
controls['b'].click(); assert.equal(created,b);
controls['[data-action="back"]'].click();
assert(picker.innerHTML.includes('>Open</span>'));
assert(!picker.innerHTML.includes('offline'));
controls['select'].change({target:{value:'b'}});
assert(picker.innerHTML.includes('/b/demo'));
assert(!picker.innerHTML.includes('/a/demo'));
controls['/b/demo'].click(); assert.equal(opened, '/b/demo');
controls['[data-action="create"]'].click(); assert.equal(created, b);
b.workspace_rows = []; workspaceTabsRenderPicker('b');
assert(picker.innerHTML.includes('No workspaces in this vault yet.'));
controls['[data-action="create"]'].click(); assert.equal(created, b);
console.log(JSON.stringify({passed:true}));
''')
    assert result['passed']


@pytest.mark.parametrize('already_listed', [False, True])
def test_creation_keeps_the_vault_selected_when_the_form_opened(already_listed):
    result = _run_node(r'''
const assert = require('assert/strict');
let _vaultCurrent = {id:'a', name:'Local'};
const controls = {};
const control = id => controls[id] ||= {
  classList:{add(){},remove(){}},reset(){},focus(){},
  elements:{namedItem:key => key === 'name' ? {value:'  New workspace  '} : null}
};
const usages = [];
const document = {getElementById:control}, window = {labFeatureUsage: name => usages.push(name)};
const setTimeout = fn => fn();
let payload, opened, workspacesList, request, finishOldCatalog;
const oldTab={vault:'a',name:'new',path:'/a/new',tab_open:true};
const newTab={vault:'b',name:'new',path:'/b/new',is_workspace:true};
const workspaceTabsAll=[oldTab];
const _vaultCatalogInFlight = new Promise(resolve=>finishOldCatalog=resolve);
const fetch = async (url, opts) => {request={url,method:opts.method};payload=JSON.parse(opts.body); return {ok:true,json:async()=>({id:'new'})};};
const fetchVaultCatalog = async () => ({vaults:[{id:'b',workspace_rows:[newTab]}]});
const goToWorkspace = path => {
  assert(workspaceTabsAll.some(row=>row.path===path),'New tab must be renderable before navigation');
  opened=path;
};
const vaultRenderWorkspacesCard = () => {};
''' + ('workspaceTabsAll.push({...newTab,tab_open:true});' if already_listed else '') + r'''
const initialTabs=workspaceTabsAll.slice();
''' + _js_between('  let _vaultWorkspaceCreateBusy = false;', '  // "Workspaces" card:') + r'''
(async()=>{
openVaultWorkspaceModal({id:'b',name:'SSD'}, '+ button');
assert.equal(controls.vaultWorkspaceContext.textContent,'SSD');
_vaultCurrent = {id:'c'};
const creating=submitVaultWorkspace();
await new Promise(resolve=>setImmediate(resolve));
assert.equal(opened,undefined,'Do not navigate using a pre-create catalog');
finishOldCatalog({vaults:[]});await creating;
assert.deepEqual(request,{url:'/api/workspaces',method:'POST'});
assert.equal(payload.vault,'b');
assert.deepEqual(usages,['Create workspace (+ button)']);
assert.deepEqual(payload,{name:'New workspace',vault:'b'});
assert.equal(opened,'/b/new');
assert.equal(workspaceTabsAll.length,2,'Do not duplicate a row discovered by polling');
assert.equal(workspaceTabsAll[0],oldTab,'Do not replace other tabs or change discovery order');
assert.equal(oldTab.tab_open,true);
assert.equal(workspaceTabsAll[1].path,'/b/new');
initialTabs.forEach((row,i)=>assert.equal(workspaceTabsAll[i],row,'Preserve existing tab identity and pending state'));
assert.equal(_vaultCurrent.id,'c');
console.log(JSON.stringify({passed:true}));
})();
''')
    assert result['passed']


@pytest.mark.parametrize('failure', [True, False])
def test_creation_does_not_remember_an_unconfirmed_workspace(failure):
    result = _run_node(r'''
const assert=require('assert/strict');
let _vaultWorkspaceCreateBusy=false, _vaultWorkspaceCreateVault='b', _vaultWorkspaceRenameTarget=null;
const _vaultWorkspaceCreateMethod='+ button', _vaultCatalogInFlight=null;
let _vaultCurrent={id:'b'},workspacesList=[],closed=0,fallback=0;
const existing={path:'/a/keep',name:'keep',tab_open:true},workspaceTabsAll=[existing];
const controls={};
const document={getElementById:id=>controls[id]||=(
  {classList:{add(){},remove(){}},elements:{namedItem:()=>({value:'New'})}}
)};
const window={};
const fetch=async()=>({ok:SUCCESS,json:async()=>SUCCESS?{id:'new'}:{detail:'Creation failed'}});
const fetchVaultCatalog=async()=>({vaults:[{id:'b',workspace_rows:[]}]});
const closeVaultWorkspaceModal=()=>closed++;
const vaultRenderWorkspacesCard=()=>fallback++;
const goToWorkspace=()=>assert.fail('Unconfirmed workspace must not open');
'''.replace('SUCCESS', 'false' if failure else 'true') + _js_between('  async function submitVaultWorkspace(', '  window.submitVaultWorkspace =') + r'''
(async()=>{
await submitVaultWorkspace();
assert.deepEqual(workspaceTabsAll,[existing]);
assert.equal(workspaceTabsAll[0],existing);
assert.equal(_vaultWorkspaceCreateBusy,false);
assert.equal(controls.vaultWorkspaceSubmit.disabled,false);
assert.equal(controls.vaultWorkspaceSubmit.textContent,'Create workspace');
if(controls.vaultWorkspaceError.textContent){
  assert.equal(controls.vaultWorkspaceError.textContent,'Creation failed');assert.equal(closed,0);assert.equal(fallback,0);
}else{assert.equal(closed,1);assert.equal(fallback,1);}
console.log(JSON.stringify({passed:true}));
})();
''')
    assert result['passed']


def test_picker_click_survives_replacing_its_contents():
    result = _run_node(r'''
const assert = require('assert/strict');
const handlers = {};
const picker = {contains:()=>false};
const document = {getElementById:()=>picker, addEventListener:(type,fn)=>handlers[type]=fn};
const window = {addEventListener(){}};
let closed = 0;
const workspaceTabsClosePicker = () => closed++;
''' + _js_between("  document.addEventListener('click', event => {\n    const picker", '  function workspaceTabsRenderPicker(') + r'''
// The New workspace button has been detached by rendering the vault list,
// but its bubbling click must keep the picker open.
const target = {closest:()=>null};
handlers.click({target,composedPath:()=>[target,picker,document]});
assert.equal(closed,0);
handlers.click({target,composedPath:()=>[target,document]});
assert.equal(closed,1);
console.log(JSON.stringify({passed:true}));
''')
    assert result['passed']
