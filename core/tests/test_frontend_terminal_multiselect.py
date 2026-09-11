"""Bulk terminal actions retain explicit session identities and scope."""
from .test_frontend_terminal_ui import _js_between, _run_node


SELECTION = _js_between('  let _termTabSelectionScope', '  function _termNormalizeGroupState')
GROUPS = _js_between('  function _termGroupScopeKey()', '  function _termSessionDisplay(s)')


def test_selection_toggle_context_target_pruning_and_scope():
    result = _run_node(r'''
let scope = 'one::demo';
const _termGroupScopeKey = () => scope;
const _termActiveWorkspaceId = () => 'demo';
let termCurrentWorkspaceId = 'demo', termCurrentSession = 'a';
let termSessions = ['a', 'b', 'c'].map(name => ({name}));
const document = {getElementById: () => null};
''' + SELECTION + r'''
const snapshots = [];
const save = () => snapshots.push([..._termTabSelection()]);
_termSelectTab('b', true); save();
_termSelectTab('c', true); save();
_termSelectTab('b', true); save();
_termSelectTab('a', false, true); save();
_termSelectTab('b', false, true); save();
_termSelectTab(null); save();
_termSelectTab('b', true);
termSessions = [{name:'b'}]; save();
scope = 'two::demo'; save();
console.log(JSON.stringify({snapshots, active: termCurrentSession}));
''')
    assert result['snapshots'] == [['a', 'b'], ['a', 'b', 'c'], ['a', 'c'],
                                   ['a', 'c'], ['b'], [], ['b'], []]
    assert result['active'] == 'a'


PRELUDE = r'''
const stored = {};
const localStorage = {getItem: key => stored[key] || null, setItem: (key, value) => stored[key] = value};
const document = {getElementById: () => null, removeEventListener() {}};
let vault = 'one', workspace = '__self__';
const _termVaultId = () => vault;
const _termActiveWorkspaceId = () => workspace;
const _termSessionsKey = (workspace, vault) => vault + '::' + workspace;
const _TERM_GROUPS_KEY = 'groups', _TERM_GROUP_COLORS = ['#58a6ff'];
let _termGroupMenuOutside = null;
let termSessions = ['a','b','c','d'].map(name => ({name,logical_name:name}));
let termCurrentSession = 'a', termCurrentWorkspaceId = workspace;
const _termSessionMeta = name => termSessions.find(s => s.name === name);
const termRenderSessionList = () => {};
let prompts = 0;
const prompt = () => {prompts++; return 'Build';};
const termSessEsc = String;
'''


def test_bulk_group_creates_once_preserves_order_and_ungroups_only_selection():
    result = _run_node(PRELUDE + GROUPS + r'''
termCreateDivider('c', 'after');
const divider = _termReadGroupState().groups[0].id;
termAssignTabGroup(['c','a'], 'new');
const grouped = _termReadGroupState();
const id = grouped.tabGroups[0].id;
termAssignTabGroup(['b','d'], id);
const moved = _termReadGroupState();
termAssignTabGroup(['a','d'], null);
const ungrouped = _termReadGroupState();
console.log(JSON.stringify({prompts, divider, grouped, moved, ungrouped}));
''')
    assert result['prompts'] == 1
    group = result['grouped']['tabGroups'][0]['id']
    assert result['grouped']['tabMembership'] == {'a': group, 'c': group}
    assert result['grouped']['order'] == ['s:a', 's:c', 's:b', 'g:' + result['divider'], 's:d']
    assert result['moved']['order'] == ['s:a', 's:c', 's:b', 's:d', 'g:' + result['divider']]
    assert result['ungrouped']['tabMembership'] == {'b': group, 'c': group}
    assert result['ungrouped']['groups'][0]['id'] == result['divider']


def test_bulk_menu_excludes_single_actions_and_captures_targets():
    result = _run_node(PRELUDE + GROUPS + r'''
let menu, handler;
_termShowGroupMenu = (anchor, html, action) => {menu = html; handler = action;};
const associations = [], closed = [];
const _termHomeAssociationOptions = () => [{id:'home',name:'Home'}, {id:'logs',name:'Logs'}];
const _termHomeAssociation = () => 'home';
const _termSaveHomeAssociation = (...args) => associations.push(args);
termCloseTabs = names => closed.push([...names]);
_termSelectTab('b', true);
termOpenTabMenu('a', {});
const bulkMenu = menu;
handler('associate:logs');
_termSelectTab('c', true);
handler('close');
workspace = 'demo';
termOpenSelectedTabsMenu(['a','b'], {});
console.log(JSON.stringify({bulkMenu, workspaceMenu: menu, associations, closed}));
''')
    assert '2 terminals selected' in result['bulkMenu']
    assert 'Close 2 tabs' in result['bulkMenu']
    assert 'Associate with' in result['bulkMenu']
    for action in ['rename', 'before', 'after', 'close-group']:
        assert f'data-action="{action}"' not in result['bulkMenu']
    assert 'Associate with' not in result['workspaceMenu']
    assert result['associations'] == [['a', 'logs'], ['b', 'logs']]
    assert result['closed'] == [['a', 'b']]


def test_bulk_unlink_retains_original_scope_and_reports_partial_failure():
    helper = _js_between('  async function termUnlinkTabs(', '  function termOpenTabGroupMenu(')
    result = _run_node(r'''
let vault = 'one';
const _termLinkContext = () => ({workspaceId:'demo',vaultId:vault});
const _termLinkedFileName = path => path?.split('/').pop();
const _termSessionDisplay = session => session.name;
const calls = [], notices = [];
const explorerToast = (...args) => notices.push(args);
const _termPatchLinks = async (session, patch, context) => {
  calls.push({name:session.name,patch,context});
  vault = 'two';
  if (session.name === 'b') throw new Error('denied');
};
''' + helper + r'''
(async () => {
await termUnlinkTabs([
{name:'a',label:'a.md',linked_file:{path:'a.md'}},
{name:'b',label:'Custom',linked_file:{path:'b.md'}},
{name:'c'},
{name:'d',linked_file:{path:'d.md'}}], 'file');
console.log(JSON.stringify({calls,notices}));
})();
''')
    assert [c['name'] for c in result['calls']] == ['a', 'b', 'd']
    assert all(c['context']['vaultId'] == 'one' for c in result['calls'])
    assert result['calls'][0]['patch'] == {'linked_file': None, 'label': None}
    assert result['calls'][1]['patch'] == {'linked_file': None}
    assert result['notices'] == [['Could not remove all links: b: denied', True]]
