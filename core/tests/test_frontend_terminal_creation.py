"""Confirmed terminal creation can attach while its live list reconciles."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parents[1] / 'src/core/static/js/lab-app.js'


def section(start, end):
    source = SOURCE.read_text()
    offset = source.index(start)
    return source[offset:source.index(end, offset)]


def run(body, **options):
    node = shutil.which('node')
    if not node:
        pytest.skip('Node required')
    helpers = '\n'.join([
        section('  const _termSessionsCache =', '  // localStorage key prefix'),
        section('  function _termIsScopeActive(', '  function _termSetPaneActive('),
        section('  async function termRefreshSessions(', '  let _termDragState'),
        section('  async function termRefreshSessionsByWorkspaceId(', '  // Live notebook execution'),
        section('  async function termSpawnSession(', '  async function termKillCurrent('),
    ])
    prelude = r'''
const assert = require('node:assert/strict');
const window = {};
const CEREBRO_WORKSPACE_ID = '__cerebro__', SELF_WORKSPACE_ID = '__self__';
const ASSISTANT_WORKSPACE_ID = '__assistant__';
const active = {workspace: options.workspace || 'demo', vault: 'ssd', home: options.home || null};
const _termActiveWorkspaceId = () => active.workspace;
const _termVaultId = () => active.vault;
const _termHomeSection = () => active.home;
const _termSessionsKey = (workspace, vault) => vault + '::' + workspace;
const _vaultQuery = vault => '&vault=' + encodeURIComponent(vault);
const _termSelectedScope = () => ({root: '/project', project_root: '/project'});
const associations = [], statuses = [], alerts = [], attachments = [], auto = [], gets = [], posts = [];
const _termSaveHomeAssociation = (...args) => associations.push(args);
const termSetStatus = (...args) => statuses.push(args);
const alert = message => alerts.push(message);
const old = {name: 'old', logical_name: 'old', workspace_id: active.workspace};
const created = {name: 'new', logical_name: 'new', kind: 'shell', cwd: '/project'};
let termSessions = [old], selected = 'old', renders = 0, termAttachRequestSeq = 0;
const termDeadSessions = new Set(['new', 'old-gone']);
const termReconnectAttempts = {'new': 2, 'old-gone': 3};
const _termClearDead = name => {termDeadSessions.delete(name); delete termReconnectAttempts[name];};
const termRenderSessionList = () => {renders++;};
let termAttach = (name, workspace) => {
  assert.ok(_termCanAttach(workspace, name), 'confirmed metadata must permit attachment');
  assert.ok(_termSessionsCache.get(_termSessionsKey(workspace, active.vault)).some(s => s.name === name));
  attachments.push([name, workspace]); selected = name;
};
function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => {resolve = yes; reject = no;});
  return {promise, resolve, reject};
}
const response = (rows, ok = true) => ({ok, json: async () => rows});
const tick = () => new Promise(setImmediate);
let postResult = Promise.resolve(response(created));
let settingResult = Promise.resolve();
const termSetAutoSpawnEnabled = (...args) => {auto.push(args); return settingResult;};
const fetch = (url, request = {}) => {
  if (request.method === 'POST') {posts.push(JSON.parse(request.body)); return postResult;}
  if (request.method === 'DELETE') return Promise.resolve(response({}));
  const pending = deferred(); gets.push({url, ...pending}); return pending.promise;
};
'''
    script = ('const options = ' + json.dumps(options) + ';\n' + prelude + helpers
              + '\n(async () => {\n' + body
              + '\n})().catch(error => {console.error(error); process.exit(1);});')
    result = subprocess.run([node, '-e', script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('workspace', ['demo', '__self__', '__cerebro__', '__assistant__'])
@pytest.mark.parametrize('outcome', ['enriched', 'missing', 'failure', 'failure_cache_invalidated'])
def test_attachment_precedes_refresh_and_retains_confirmed_identity(workspace, outcome):
    run(r'''
const origin = active.workspace;
const pending = termSpawnSession('shell', {startFresh: true});
await tick();
assert.equal(gets.length, 1);
assert.ok(gets[0].url.includes('workspace_id=' + encodeURIComponent(origin)));
assert.deepEqual(attachments, [['new', origin]]);
assert.equal(termSessions[0].workspace_id, origin);
assert.equal(termSessions[0].cwd, '/project');
assert.ok(!termDeadSessions.has('new'));
assert.equal(termReconnectAttempts.new, undefined);
assert.deepEqual(auto, [[origin, true, 'ssd']]);
assert.equal(posts[0].linked_scope.root, '/project');
assert.equal(posts[0].vault, 'ssd');
// User intent after the new terminal opens must survive delayed reconciliation.
selected = 'old';
const enriched = {...created, workspace_id: origin, label: 'Server label', summary: 'Live summary'};
// A completed metadata update from another workspace can clear the warm cache.
if (options.outcome === 'failure_cache_invalidated') _termSessionsCache.clear();
gets[0].resolve(options.outcome.startsWith('failure') ? response([], false)
  : response(options.outcome === 'missing' ? [old] : [old, enriched]));
assert.deepEqual(await pending, created);
assert.equal(attachments.length, 1);
assert.equal(selected, 'old');
assert.equal(termSessions.filter(s => s.name === 'new').length, 1);
assert.deepEqual(_termSessionsCache.get(_termSessionsKey(origin, 'ssd')), termSessions);
if (options.outcome === 'enriched') assert.equal(_termSessionMeta('new').label, 'Server label');
assert.deepEqual(alerts, []);
''', workspace=workspace, outcome=outcome)


@pytest.mark.parametrize('workspace', ['demo', '__self__'])
@pytest.mark.parametrize('delayed_part', ['fetch', 'json'])
def test_pre_creation_read_cannot_erase_new_session_or_reconnect_bookkeeping(workspace, delayed_part):
    run(r'''
const refresh = active.workspace === 'demo' ? termRefreshSessions : termRefreshSessionsByWorkspaceId;
const oldRead = refresh(active.workspace);
const oldBody = deferred();
if (options.delayed_part === 'json') {
  gets[0].resolve({ok: true, json: () => oldBody.promise});
  await tick();
}
const pending = termSpawnSession('shell', {startFresh: true});
await tick();
assert.equal(gets.length, 2);
const before = renders;
if (options.delayed_part === 'json') oldBody.resolve([old]);
else gets[0].resolve(response([old]));
assert.equal(await oldRead, true);
assert.equal(renders, before);
assert.ok(_termCanAttach(active.workspace, 'new'), 'assets can finish after the stale GET');
assert.ok(_termSessionsCache.get(_termSessionsKey(active.workspace, 'ssd')).some(s => s.name === 'new'));
assert.ok(termDeadSessions.has('old-gone'));
assert.equal(termReconnectAttempts['old-gone'], 3);
gets[1].resolve(response([old, {...created, label: 'Fresh'}]));
await pending;
assert.equal(_termSessionMeta('new').label, 'Fresh');
assert.ok(!termDeadSessions.has('old-gone'));
assert.equal(termReconnectAttempts['old-gone'], undefined);
''', workspace=workspace, delayed_part=delayed_part)


@pytest.mark.parametrize('change', ['workspace', 'vault', 'home'])
@pytest.mark.parametrize('phase', ['post', 'setting', 'refresh'])
def test_creation_keeps_origin_when_navigation_changes(change, phase):
    run(r'''
const gate = deferred();
if (options.phase === 'post') postResult = gate.promise;
if (options.phase === 'setting') settingResult = gate.promise;
const pending = termSpawnSession('shell', {startFresh: true});
await tick();
assert.equal(attachments.length, options.phase === 'refresh' ? 1 : 0);
active[options.change] = 'elsewhere';
termSessions = [{name: 'destination', workspace_id: active.workspace}];
const before = renders;
if (options.phase === 'post') gate.resolve(response(created));
else if (options.phase === 'setting') gate.resolve();
else gets[0].resolve(response([]));
await pending;
assert.equal(attachments.length, options.phase === 'refresh' ? 1 : 0);
// Home shares a scope: its confirmed session remains, without stealing selection.
assert.deepEqual(termSessions.map(s => s.name), options.change === 'home' && options.phase === 'refresh'
  ? ['new'] : ['destination']);
assert.equal(renders, before + (options.change === 'home' && options.phase === 'refresh' ? 1 : 0));
assert.deepEqual(associations, [['new', 'vault:ssd']]);
assert.deepEqual(auto, [['__self__', true, 'ssd']]);
assert.deepEqual(alerts, []);
''', workspace='__self__', home='vault:ssd', change=change, phase=phase)


def test_failed_creation_never_publishes_or_attaches():
    run(r'''
postResult = Promise.resolve(response({detail: 'Cannot create'}, false));
await termSpawnSession('shell', {startFresh: true});
assert.deepEqual(attachments, []);
assert.deepEqual(gets, []);
assert.deepEqual(auto, []);
assert.equal(_termSessionsCache.size, 0);
assert.equal(_termSessionListVersions.size, 0);
assert.deepEqual(termSessions, [old]);
assert.deepEqual(alerts, ['Failed to create session: Cannot create']);
''')


def test_second_creation_supersedes_older_read_without_affecting_other_scope():
    run(r'''
const foreign = termRefreshSessions('other');
const first = termSpawnSession('shell', {startFresh: true});
await tick();
postResult = Promise.resolve(response({name: 'second', logical_name: 'second'}));
const second = termSpawnSession('shell', {startFresh: true});
await tick();
assert.equal(gets.length, 3);
gets[0].resolve(response([{name: 'foreign'}]));
await foreign;
assert.deepEqual(_termSessionsCache.get('ssd::other'), [{name: 'foreign'}]);
gets[1].resolve(response([old, created]));
await first;
assert.ok(_termCanAttach('demo', 'second'));
assert.equal(selected, 'second');
gets[2].resolve(response([old, created, {name: 'second', label: 'Second enriched'}]));
await second;
assert.equal(_termSessionMeta('second').label, 'Second enriched');
assert.deepEqual(attachments, [['new', 'demo'], ['second', 'demo']]);
assert.equal(termSessions.length, 3);
''')


@pytest.mark.parametrize('close', ['current', 'tabs', 'all'])
@pytest.mark.parametrize('stale_includes_created', [False, True])
def test_closing_created_terminal_while_creation_refresh_waits_keeps_it_closed(close, stale_includes_created):
    run(section('  async function termKillCurrent(', '  async function termCopyAttachCmd(')
        + section('  const _termCloseTabsPending', '  function _termSessionDisplay(s)') + r'''
let termCurrentSession = 'new';
const confirm = () => true;
const termDetach = () => {termCurrentSession = null;};
const termShowEmpty = () => {};
const document = {getElementById: () => null};
const currentWorkspace = {name: 'demo'};
const _workspaceDisplayName = workspace => workspace.name;
const _termEvictCache = () => {};
const _termRefreshSessionsForWorkspaceId = termRefreshSessions;
const pending = termSpawnSession('shell', {startFresh: true});
await tick();
assert.equal(selected, 'new');
const closing = options.close === 'current' ? termKillCurrent()
  : options.close === 'tabs' ? termCloseTabs(['new']) : termKillAll();
await tick();
assert.equal(gets.length, 2);
const remaining = options.close === 'all' ? [] : [old];
gets[1].resolve(response(remaining));
await closing;
assert.deepEqual(termSessions, remaining);
// The older create refresh lands after the confirmed close and its fresh list.
gets[0].resolve(response(options.stale_includes_created ? [old, created] : remaining));
await pending;
assert.deepEqual(termSessions, remaining, 'a completed close must not regain a ghost pill');
assert.deepEqual(_termSessionsCache.get('ssd::demo'), remaining);
assert.deepEqual(alerts, []);
''', close=close, stale_includes_created=stale_includes_created)


@pytest.mark.parametrize('workspace', ['demo', '__self__'])
def test_missing_refresh_row_cannot_cancel_attachment_at_asset_completion(workspace):
    attach = section('  async function termAttach(', '    // Preserve the requested warm pane')
    run(r'''
const assets = deferred(), body = deferred();
const ensureTerminalLibs = () => assets.promise;
const _termCache = new Map(), _termCacheKey = (workspace, name) => workspace + '::' + name;
const termCurrentSession = 'old', termCurrentWorkspaceId = active.workspace, termWS = null;
const _termRememberLast = () => {};
let attaching;
const startAttachment = (''' + attach + r'''
    return true;
  });
termAttach = (...args) => {attaching = startAttachment(...args); return attaching;};
const pending = termSpawnSession('shell', {startFresh: true});
await tick();
gets[0].resolve({ok: true, json: () => body.promise});
await tick();
// Both promises become ready in one task: refresh publishes before the
// attachment's continuation, but spawn's continuation runs after it.
body.resolve([]);
assets.resolve();
await pending;
assert.equal(await attaching, true, 'a confirmed row must remain attachable across refresh publication');
assert.ok(_termCanAttach(active.workspace, 'new'));
assert.deepEqual(alerts, []);
''', workspace=workspace)
