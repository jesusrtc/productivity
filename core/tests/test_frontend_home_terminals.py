"""Home sections share terminal ownership without changing their file roots."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parents[1] / 'src/core/static/js/lab-app.js'


def section(start, end):
    source = SOURCE.read_text()
    return source[source.index(start):source.index(end, source.index(start))]


def run(body, *extra):
    node = shutil.which('node')
    if not node:
        pytest.skip('node required')
    helpers = '\n'.join([
        section('  function _termHomeViewActive()', '  // Which tab (if any)'),
        section('  function _termActiveWorkspaceId()', '  async function termAutoSpawnEnabled'),
        section('  function _termVisibilityKey()', '  function _termRememberVisibility'),
    ])
    prelude = '''
const classes = new Set();
const document = {body: {classList: {
  contains: name => classes.has(name),
  add: (...names) => names.forEach(name => classes.add(name)),
  remove: (...names) => names.forEach(name => classes.delete(name)),
}}, getElementById: () => null};
let LAB_IS_ADMIN = true;
let _contextSubView = 'overview', vaultCatalog = [], termSessions = [];
const storage = new Map();
const localStorage = {getItem: k => storage.get(k) || null, setItem: (k, v) => storage.set(k, v)};
const SELF_WORKSPACE_ID = '__self__', CEREBRO_WORKSPACE_ID = '__cerebro__';
const ASSISTANT_WORKSPACE_ID = '__assistant__', ASSISTANT_VAULT_ID = '__assistant__';
const _TERM_VIS_KEY_PREFIX = 'visibility:';
let currentWorkspace = null, currentRepo = null, currentRepoInWorkspace = null;
const _workspaceVaultId = workspace => workspace?.vault_id || null;
function view(name, workspace) { classes.clear(); classes.add(name + '-active'); currentWorkspace = workspace; }
'''
    result = subprocess.run([node, '-e', prelude + '\n(async () => {' + helpers + '\n'.join(extra) + body + '})().catch(e => { console.error(e); process.exit(1); });'],
                            capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def test_home_sections_share_scope_settings_and_visibility():
    result = run('''
const home = [];
for (const [name, root] of [['self', '/framework'], ['vault', '/ssd'], ['vault', '/local']]) {
  view(name, {name: name === 'vault' ? '__vault__' : '__self__', path: root, vault_id: root, is_workspace: true});
  home.push([_termActiveWorkspaceId(), _termVaultId(), _termSessionsKey(_termActiveWorkspaceId()), _termVisibilityKey(), currentWorkspace.path]);
}
view('workspace', {name: 'demo', vault_id: 'ssd', is_workspace: true});
const workspace = [_termActiveWorkspaceId(), _termVaultId()];
view('assistant', {});
const assistant = [_termActiveWorkspaceId(), _termVaultId()];
LAB_IS_ADMIN = false;
view('vault', {name: '__vault__', vault_id: 'local', is_workspace: true});
console.log(JSON.stringify({home, workspace, assistant, restricted: _termActiveWorkspaceId()}));
''')
    assert [row[:4] for row in result['home']] == [
        ['__self__', None, 'framework::__self__', 'visibility:self']
    ] * 3
    assert [row[4] for row in result['home']] == ['/framework', '/ssd', '/local']
    assert result['workspace'] == ['demo', 'ssd']
    assert result['assistant'] == ['__assistant__', '__assistant__']
    assert result['restricted'] is None


def test_home_section_switch_keeps_the_mounted_terminal():
    result = run('''
let _workspaceDeleteTarget = null;
const closeVaultWorkspaceMenu = () => {};
const calls = [];
const termDetach = () => calls.push('detach');
const _termIsScopeActive = id => id === _termActiveWorkspaceId();
const _termApplyRememberedVisibility = () => {};
const termStartPeriodicRefresh = () => {};
const _termTryWarmOpen = async () => { calls.push('warm'); return false; };
const _termRestoreSessionsForWorkspace = async () => calls.push('restore');
const termCurrentWorkspaceId = '__self__', termCurrentSession = 'existing-home-session';
for (const name of ['self', 'vault', 'vault']) {
  view(name, {name: '__vault__'});
  _swapViewState({preserveHomeTerminal: true});
  view('vault', {name: '__vault__'});
  await termOpenForSelf();
}
const homeCalls = [...calls];
_swapViewState();
console.log(JSON.stringify({homeCalls, leaving: calls}));
''', section('  function _swapViewState(', '  // Navigate to a real workspace'),
        section('  async function termOpenForSelf()', '  // ─── Vault view'))
    assert result == {'homeCalls': [], 'leaving': ['detach']}


def test_new_session_and_polling_target_home_from_a_vault():
    result = run('''
view('vault', {name: '__vault__', vault_id: 'ssd', is_workspace: true});
classes.add('term-open');
const requests = [], refreshes = [];
const _termSelectedScope = () => ({root: '/selected/project', project_root: '/selected/project'});
const fetch = async (url, opts) => {
  requests.push(JSON.parse(opts.body));
  return {ok: true, json: async () => ({name: 'new-home-terminal'})};
};
const termSetStatus = () => {}, _termClearDead = () => {}, termRenderSessionList = () => {};
const alert = message => { throw new Error(message); };
const termSetAutoSpawnEnabled = async () => {};
const termRefreshSessionsByWorkspaceId = async id => refreshes.push(id);
const termRefreshSessions = async id => refreshes.push(id);
const _termIsScopeActive = id => id === _termActiveWorkspaceId();
const _termSessionsCache = new Map();
let termSessions = [];
const termAttach = () => {};
await termSpawnSession('shell', {startFresh: true});
let tick, termRefreshTimer = null, _termReorderPending = false;
const termCurrentSession = null, termCurrentWorkspaceId = null;
const setInterval = fn => { tick = fn; return 1; };
const _termRefreshSessionsForWorkspaceId = async id => { refreshes.push(id); return true; };
const termStopPeriodicRefresh = () => {};
termStartPeriodicRefresh();
await tick();
console.log(JSON.stringify({requests, refreshes}));
''', section('  async function termSpawnSession(', '  async function termKillCurrent()'),
        section('  function termStartPeriodicRefresh()', '  function termStopPeriodicRefresh()'))
    assert result['requests'][0]['workspace_id'] == '__self__'
    assert result['requests'][0]['vault'] is None
    assert result['requests'][0]['cwd'] == '/selected/project'
    assert result['requests'][0]['linked_scope']['project_root'] == '/selected/project'
    assert result['refreshes'] == ['__self__', '__self__']


def test_home_navigation_restores_each_sections_latest_terminal():
    result = run('''
vaultCatalog = [{id: 'ssd', name: 'SSD', path: '/ssd', color: '#ff8800'},
  {id: 'local', name: 'Local', path: '/local', color: '#5588ff'}];
termSessions = [
  {name: 'home', logical_name: 'home'},
  {name: 'ssd-old', logical_name: 'ssd-old', linked_scope: {root: '/ssd/project'}},
  {name: 'ssd-new', logical_name: 'ssd-new'},
  {name: 'local', logical_name: 'local', linked_scope: {root: '/local'}},
  {name: 'logs', logical_name: 'logs'},
];
_termSaveHomeAssociation('ssd-old', 'vault:ssd', 100);
_termSaveHomeAssociation('ssd-new', 'vault:ssd', 200);
_termSaveHomeAssociation('logs', 'logs', 300);
const selected = [];
const termAttach = name => selected.push(name);
view('self', {});
_termSelectHomeSection();
view('vault', {vault_id: 'ssd'});
_termSelectHomeSection();
view('vault', {vault_id: 'local'});
_termSelectHomeSection();
view('self', {}); _contextSubView = 'logs';
_termSelectHomeSection();
// A reload reads the same durable associations, and closing the newest
// session falls back to the remaining session for that vault.
view('vault', {vault_id: 'ssd'});
const restored = _termHomeRestoreName();
termSessions = termSessions.filter(s => s.name !== 'ssd-new');
const fallback = _termHomeRestoreName();
_termSaveHomeAssociation('ssd-old', 'home', 400);
const reassigned = _termHomeRestoreName();
const termSessEsc = value => value;
view('self', {});
const badge = _termHomeAssociationHtml(termSessions.find(s => s.name === 'logs'));
console.log(JSON.stringify({selected, restored, fallback, reassigned, badge}));
''')
    assert result['selected'] == ['home', 'ssd-new', 'local', 'logs']
    assert result['restored'] == 'ssd-new'
    assert result['fallback'] == 'ssd-old'
    assert result['reassigned'] is None
    assert '#f85149' in result['badge']
    assert 'Logs' in result['badge']


def test_creation_keeps_origin_association_when_home_section_changes():
    result = run('''
view('vault', {vault_id: 'ssd'});
const _termSelectedScope = () => null;
const termSetStatus = () => {}, alert = message => {throw Error(message);};
const termSetAutoSpawnEnabled = async () => {};
const fetch = async () => {
  view('self', {}); _contextSubView = 'logs';
  return {ok: true, json: async () => ({name: 'new-ssd', logical_name: 'new-ssd'})};
};
const attached = [];
const termAttach = name => attached.push(name);
await termSpawnSession('shell', {startFresh: true});
console.log(JSON.stringify({association: _termReadHomeAssociations()['new-ssd'].section, attached}));
''', section('  async function termSpawnSession(', '  async function termKillCurrent()'))
    assert result == {'association': 'vault:ssd', 'attached': []}


def test_using_a_home_terminal_updates_its_own_sections_recency():
    result = run('''
const TERM_LAST_KEY = 'last';
vaultCatalog = [{id: 'ssd', path: '/ssd'}];
termSessions = [{name: 'one', logical_name: 'one'}, {name: 'two', logical_name: 'two'}];
_termSaveHomeAssociation('one', 'vault:ssd', 100);
_termSaveHomeAssociation('two', 'vault:ssd', 200);
// Manually selecting an SSD terminal while viewing Logs updates SSD's last
// selection without relabeling the process as a Logs terminal.
view('self', {}); _contextSubView = 'logs';
_termRememberLast('__self__', 'one');
view('vault', {vault_id: 'ssd'});
console.log(JSON.stringify({selected: _termHomeRestoreName(), section: _termReadHomeAssociations().one.section}));
''', section('  function _termRememberLast(', '  function _termRecallLast('))
    assert result == {'selected': 'one', 'section': 'vault:ssd'}
