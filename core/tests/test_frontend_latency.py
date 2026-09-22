"""Polling preserves DOM identity and only repaints visible changes."""
from .test_frontend_terminal_ui import _js_between, _run_node


def test_terminal_poll_preserves_nodes_but_updates_changed_state():
    render = _js_between('  function termRenderSessionList()', '  // One move plan')
    result = _run_node(r'''
let paints = 0, hides = 0, wires = 0;
const el = {set innerHTML(value) { paints++; this.markup = value; this.node = {}; }, querySelectorAll: () => []};
const document = {getElementById: () => el};
let _termDragState = null;
let termSessions = [{name: 'one', logical_name: 'one', label: 'Original'}];
let termCurrentSession = 'one';
let state = {order: ['s:one'], groups: [], tabGroups: [], tabMembership: {}};
const _termReadGroupState = () => state;
const _termReconcileGroupOrder = state => state.order;
const _termRenderActiveSessionHeader = () => {};
const _termSyncTabSelection = () => {};
const _termHideSessionTooltip = () => hides++;
const _termNewButtonHtml = () => '<button>New</button>';
const _termSessionPillHtml = row => row.label + ':' + (row.name === termCurrentSession);
const termWireSessionDnD = () => wires++;
const termSessEsc = String;
''' + render + r'''
termRenderSessionList();
const first = el.node;
for (let i = 0; i < 100; i++) termRenderSessionList();
const stable = {paints, hides, wires, sameNode: first === el.node};
termSessions = [{...termSessions[0], label: 'Renamed'}];
termRenderSessionList();
const renamed = el.markup;
termCurrentSession = 'other';
termRenderSessionList();
const selected = el.markup;
termSessions = [];
termRenderSessionList();
termRenderSessionList();
console.log(JSON.stringify({stable, renamed, selected, paints, hides, wires, empty: el.markup}));
''')
    assert result['stable'] == dict(paints=1, hides=1, wires=1, sameNode=True)
    assert result['renamed'].startswith('Renamed:true')
    assert result['selected'].startswith('Renamed:false')
    assert result['paints'] == 4
    assert result['empty'] == '<button>New</button>'


def test_workspace_poll_preserves_nodes_and_repaints_navigation():
    render = _js_between('  function workspaceTabsRender()', '  function workspaceTabsWireDnD')
    result = _run_node(r'''
let paints = 0;
const el = {set innerHTML(value) {paints++; this.markup = value; this.node = {};}, querySelectorAll: () => []};
const classes = new Set(['self-active']);
const document = {getElementById: () => el, body: {classList: {contains: key => classes.has(key)}}};
const SELF_WORKSPACE_ID = '__self__', ASSISTANT_WORKSPACE_ID = '__assistant__', LAB_IS_ADMIN = true;
let currentWorkspace = null;
let workspaceTabsOrder = [], workspaceTabsOrderReady = true, workspaceTabsDragId = null;
const workspaceTabsSaveOrder = () => {}, workspaceTabsWireDnD = () => {};
let workspaceTabsAll = [{path: '/demo', name: 'demo', display_name: 'Demo', vault: 'vault'}];
const workspaceTabsOpenIds = () => ['/demo'];
const _vaultForWorkspace = () => ({name: 'Vault', color: '#ffffff'});
const workspaceTabsEsc = String;
const _workspaceDisplayName = row => row.display_name;
const tabBlocked = {};
''' + render + r'''
workspaceTabsRender();
const first = el.node;
for (let i = 0; i < 100; i++) workspaceTabsRender();
const stable = {paints, sameNode: first === el.node};
workspaceTabsAll[0].display_name = 'Renamed';
workspaceTabsRender();
const renamed = el.markup.includes('Renamed');
classes.delete('self-active'); classes.add('workspace-active');
currentWorkspace = workspaceTabsAll[0];
workspaceTabsRender();
console.log(JSON.stringify({stable, renamed, paints, active: el.markup.includes('vault-owned active')}));
''')
    assert result['stable'] == dict(paints=1, sameNode=True)
    assert result['renamed'] and result['active']
    assert result['paints'] == 3


def test_workspace_click_during_startup_does_not_wait_for_page_quiet():
    """A user can act as soon as tabs appear, before startup's quiet window."""
    scheduling = _js_between('  function afterPageQuiet(', '  const _assetPromises')
    selection = _js_between('  async function selectRepo(', '  async function loadDiff()')
    result = _run_node(r'''
const calls = [], timers = [];
const performance = {now: () => 500};
const setTimeout = callback => timers.push(callback);
const location = {search: ''};
window.location = 'http://localhost/?view=productivity';
const history = {replaceState: () => {}};
const document = {
  readyState: 'complete', title: '',
  body: {classList: {add: () => {}, remove: () => {}}},
  getElementById: () => ({style: {}}),
};
let currentWorkspace, _workspaceDeleteTarget = null, _contextSubView;
let currentRepo, currentRepoInWorkspace, _workspaceDocPath;
const workspacesList = [{name: 'alpha', path: '/alpha', is_workspace: true},
                        {name: 'beta', path: '/beta', is_workspace: true}];
const _sidebarActivateFileConfig = () => {};
const _workspaceMarkUsed = () => {};
const workspaceTabsSetOpen = () => {};
const _workspaceDisplayName = w => w.name;
const renderRepoTabs = () => {};
const refreshAttrsBar = () => calls.push('attrs:' + currentWorkspace.name);
const showWorkspaceInfo = () => calls.push('dashboard:' + currentWorkspace.name);
const getLastWorkspaceDoc = path => path === '/beta' ? 'docs/review.md' : null;
const paintWorkspaceShell = () => calls.push('shell:' + currentWorkspace.name);
const openWorkspaceDoc = path => calls.push('doc:' + path);
const _termIsScopeActive = id => currentWorkspace.name === id;
const termOpenForWorkspace = id => calls.push('terminal:' + id);
const workspaceTabsRender = () => {};
''' + scheduling + selection + r'''
(async () => {
  await selectRepo('/alpha');
  const firstClick = {calls: [...calls], timers: timers.length};
  calls.length = 0;
  await selectRepo('/beta');
  const remembered = {calls: [...calls], doc: _workspaceDocPath, timers: timers.length};
  calls.length = 0;
  await selectRepo('/alpha', {initialLoad: true});
  const initial = {calls: [...calls], timers: timers.length};
  calls.length = 0;
  await selectRepo('/beta');
  calls.length = 0;
  for (const timer of timers.splice(0)) timer();
  console.log(JSON.stringify({firstClick, remembered, initial, late: calls}));
})();
''')
    assert result['firstClick'] == {
        'calls': ['shell:alpha', 'attrs:alpha', 'dashboard:alpha', 'terminal:alpha'],
        'timers': 0,
    }
    assert result['remembered'] == {
        'calls': ['attrs:beta', 'dashboard:beta', 'doc:docs/review.md', 'terminal:beta'],
        'doc': 'docs/review.md', 'timers': 0,
    }
    assert result['initial'] == {'calls': ['shell:alpha'], 'timers': 2}
    assert 'terminal:alpha' not in result['late']
