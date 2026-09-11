"""The new-tab picker routes workspaces and creation to their owning vault."""
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


def test_creation_keeps_the_vault_selected_when_the_form_opened():
    result = _run_node(r'''
const assert = require('assert/strict');
let _vaultCurrent = {id:'a', name:'Local'};
const controls = {};
const control = id => controls[id] ||= {
  classList:{add(){},remove(){}},reset(){},focus(){},
  elements:Object.fromEntries(['id','description','priority','due','tags','labels'].map(k=>[k,{value:k==='id'?'new':''}]))
};
const document = {getElementById:control}, window = {};
const setTimeout = fn => fn();
let payload, opened, workspacesList;
const _vaultCatalogInFlight = null;
const fetch = async (url, opts) => {payload=JSON.parse(opts.body); return {ok:true,json:async()=>({id:'new'})};};
const fetchVaultCatalog = async () => ({vaults:[{id:'b',workspace_rows:[{vault:'b',name:'new',path:'/b/new'}]}]});
const goToWorkspace = path => opened=path;
const vaultRenderWorkspacesCard = () => {};
''' + _js_between('  let _vaultWorkspaceCreateBusy = false;', '  // "Workspaces" card:') + r'''
(async()=>{
openVaultWorkspaceModal({id:'b',name:'SSD'});
assert.equal(controls.vaultWorkspaceContext.textContent,'SSD');
_vaultCurrent = {id:'c'};
await submitVaultWorkspace();
assert.equal(payload.vault,'b');
assert.equal(opened,'/b/new');
assert.equal(_vaultCurrent.id,'c');
console.log(JSON.stringify({passed:true}));
})();
''')
    assert result['passed']
