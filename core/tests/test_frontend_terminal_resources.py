"""Browser terminal resources must be bounded without ending tmux work."""
import json
from pathlib import Path
import shutil
import subprocess

import pytest

SOURCE = Path(__file__).resolve().parents[1] / 'src/core/static/js/lab-app.js'


def section(start, end):
    source = SOURCE.read_text()
    offset = source.index(start)
    return source[offset:source.index(end, offset)]


def run(body, *helpers):
    node = shutil.which('node')
    if not node:
        pytest.skip('Node required')
    prelude = r'''
const assert = require('node:assert/strict');
const console = {log() {}, warn() {}};
const handlers = {};
const window = {addEventListener: (name, fn) => handlers[name] = fn};
let now = 1000, timerId = 0;
const timers = new Map();
const Date = {now: () => now};
const setTimeout = (fn, delay) => { timers.set(++timerId, {fn, at: now + delay}); return timerId; };
const clearTimeout = id => timers.delete(id);
function advance(ms) {
  now += ms;
  for (const [id, timer] of [...timers]) {
    if (timer.at <= now) { timers.delete(id); timer.fn(); }
  }
}
const document = {getElementById: () => null};
const WebSocket = {OPEN: 1};
let termXterm = null, termWS = null, termContainer = null, termFitAddon = null;
let termCurrentSession = null, termCurrentWorkspaceId = null;
let termAttachRequestSeq = 0, termUserDetached = false, termReconnectTimer = null;
const _termActiveWorkspaceId = () => 'demo';
const _termCacheKey = (workspace, name) => workspace + '::' + name;
const _termSetPaneActive = () => {};
const _termCache = new Map();
const TERM_FAST_PARK_MS = 600000, TERM_MAX_PARKED_PANES = 3;
let termCachePruneTimer = null;
const _termDisableWebgl = xt => { if (xt) xt.gpuReleased = true; };
const records = [];
function pane(name, workspaceId = 'demo') {
  const record = {name, workspaceId, disposed: 0, removed: 0, closed: 0, sent: [],
    parkedAt: now};
  record.xterm = {dispose: () => record.disposed++};
  record.container = {remove: () => record.removed++};
  record.ws = {readyState: 1, onclose: () => { throw Error('unwanted reconnect'); },
    send: msg => record.sent.push(JSON.parse(msg)),
    close() { record.closed++; this.readyState = 3; this.onclose?.(); }};
  records.push(record);
  return record;
}
function activate(p) {
  termCurrentSession = p.name; termCurrentWorkspaceId = p.workspaceId;
  termXterm = p.xterm; termWS = p.ws; termContainer = p.container;
}
'''
    result = subprocess.run([node, '-e', prelude + '\n'.join(helpers) + body],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def lifecycle_helpers():
    return (section('  function termDetach(', '  // Compute the next reconnect delay'),
            section('  // Disconnect only the browser view;', '  async function termAttach('))


def test_closing_an_active_uncached_view_releases_all_resources():
    run(r'''
const active = pane('active'); activate(active);
assert.equal(_termCache.size, 0);
termDetach();
assert.equal(active.closed, 1);
assert.equal(active.disposed, 1);
assert.equal(active.removed, 1);
assert.equal(active.xterm.gpuReleased, true);
assert.deepEqual(active.sent, [{type: 'detach'}]);
assert.equal(termXterm, null);
assert.equal(termContainer, null);
assert.equal(timers.size, 0);
''', *lifecycle_helpers())


def test_many_tabs_remain_bounded_and_expire_without_revisiting():
    run(r'''
for (let i = 0; i < 80; i++) {
  activate(pane('session-' + i));
  termDetach(true);
  assert.ok(_termCache.size <= TERM_MAX_PARKED_PANES);
  assert.ok(timers.size <= 1);
  now++;
}
assert.deepEqual([..._termCache.values()].map(p => p.name),
  ['session-77', 'session-78', 'session-79']);
const active = pane('still-working'); activate(active);
advance(TERM_FAST_PARK_MS);
assert.equal(_termCache.size, 0);
assert.equal(timers.size, 0);
assert.equal(active.disposed, 0);
for (const p of records.slice(0, -1)) {
  assert.equal(p.disposed, 1); assert.equal(p.closed, 1); assert.equal(p.removed, 1);
  assert.deepEqual(p.sent, [{type: 'detach'}]);
}
''', *lifecycle_helpers())


def test_switch_target_is_kept_while_oldest_other_view_is_evicted():
    run(r'''
for (const name of ['target', 'oldest-other', 'recent', 'newer', 'current']) {
  activate(pane(name)); termDetach(true, 'demo::target'); now++;
}
assert.ok(_termCache.has('demo::target'));
assert.equal(_termCache.size, 4); // The target is about to leave the parked cache.
assert.equal(records.find(p => p.name === 'oldest-other').disposed, 1);
const target = _termCache.get('demo::target');
_termCache.delete('demo::target'); activate(target);
assert.equal(_termCache.size, 3);
const broken = records.find(p => p.name === 'recent'); broken.ws.readyState = 3;
_termPruneCache();
assert.equal(broken.disposed, 1);
advance(TERM_FAST_PARK_MS);
assert.equal(records[0].disposed, 0);
assert.equal(termXterm, target.xterm);
''', *lifecycle_helpers())


def test_disposal_cancels_resize_and_disconnects_observer():
    source = SOURCE.read_text()
    start = source.index('    let _resizeTimer = null;', source.index('  async function termAttach('))
    resize = source[start:source.index('    termXterm.onData(', start)]
    run(r'''
let disposed = 0, disconnected = 0, fits = 0, resizes = 0, notifyResize;
const termSendResize = () => resizes++;
class ResizeObserver {
  constructor(fn) { notifyResize = fn; }
  observe() {}
  disconnect() { disconnected++; }
}
const myContainer = termContainer = {};
termFitAddon = {fit: () => fits++};
termXterm = {rows: 20, cols: 80, dispose: () => disposed++, _core: {viewport: {}}};
_termGuardViewportDisposal(termXterm);
''' + resize + r'''
notifyResize();
assert.equal(timers.size, 1);
termXterm.dispose(); termXterm.dispose();
advance(1000);
assert.equal(disconnected, 1);
assert.equal(disposed, 1);
assert.equal(fits, 0); assert.equal(resizes, 0);
assert.equal(timers.size, 0);
''', section('  function _termGuardViewportDisposal(', '  function termEnsureXterm('))


@pytest.mark.parametrize('failure', ['context', 'activation', 'render', 'disposed'])
def test_gpu_failure_repaints_the_owner_and_stops_retrying(failure):
    # GPU helpers supply their own disable function; no lifecycle stubs here.
    source = section('  let _termWebglFailed', '  function termShowEmpty()')
    source = source.replace('function _termDisableWebgl(', 'function disableGpu(')
    source = source.replace('_termDisableWebgl(', 'disableGpu(')
    run(r'''
let created = 0, disposed = 0;
const WebglAddon = {WebglAddon: class {
  constructor() { created++; }
  onContextLoss(fn) { this.lost = fn; }
  dispose() { disposed++; }
}};
function terminal() { return {rows: 20, repaints: [], loadAddon() {},
  refresh(a,b) { this.repaints.push([a,b]); }}; }
const a = termXterm = terminal(), b = terminal();
const failure = FAILURE;
if (failure === 'activation') a.loadAddon = () => { throw Error('no WebGL'); };
_termEnableWebgl();
if (failure === 'context') {
  const addon = a._webglAddon;
  termXterm = b; // A late context-loss callback must still clean up A.
  addon.lost();
} else if (failure === 'disposed') {
  const addon = a._webglAddon;
  disableGpu(a);
  termXterm = b;
  addon.lost(); // A queued event from an already disposed context is harmless.
} else if (failure === 'render') {
  handlers.error({filename: 'xterm-addon-webgl.js', message: 'loadCell'});
}
assert.equal(a._webglAddon, null);
assert.deepEqual(a.repaints, [[0, 19]]);
assert.deepEqual(b.repaints, []);
termXterm = b; _termEnableWebgl();
assert.equal(created, failure === 'disposed' ? 2 : 1); assert.equal(disposed, 1);
'''.replace('FAILURE', json.dumps(failure)), source)
