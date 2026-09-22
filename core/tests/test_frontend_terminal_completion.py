import pytest

from .test_frontend_terminal_ui import _run_node, _js_between, ROOT


MODULE = (ROOT / 'core/src/core/static/js/lib/terminal-completion.js').read_text()
CLOCK = r"""
const values = {}, windowEvents = {}, documentEvents = {}, timers = new Map();
const localStorage = {getItem: key => values[key], setItem: (key, value) => values[key] = value};
let clock = 0, nextTimer = 0, focused = true, view = null;
const performance = {now: () => clock};
const setTimeout = (fn, ms) => {const id = ++nextTimer; timers.set(id, {fn, at:clock + ms}); return id;};
const clearTimeout = id => timers.delete(id);
const advance = ms => {
  clock += ms;
  for (const [id, timer] of [...timers]) if (timer.at <= clock) {timers.delete(id); timer.fn();}
};
window.addEventListener = (event, fn) => windowEvents[event] = fn;
const document = {hidden:false, hasFocus:()=>focused,
  addEventListener:(event, fn)=>documentEvents[event] = fn};
function termRenderSessionList() {
  if (!view || document.hidden || !focused) window.LabTerminalCompletion.stopViewing();
  else window.LabTerminalCompletion.watch(view.scope, view.session);
}
function show(scope, session) {view = {scope, session}; termRenderSessionList();}
function leave() {view = null; window.LabTerminalCompletion.stopViewing();}
function session(agent = 'codex', completed_at = 100, name = 'one') {
  return {name, agent, agent_session_id:'thread-'+name, created_at:1,
    agent_activity:{state:'completed', completed_at, completion_id:'turn-'+completed_at}};
}
const assert = (ok, message) => {if (!ok) throw Error(message);};
"""


@pytest.mark.parametrize('agent', ['codex', 'claude', 'copilot'])
def test_requires_twenty_seconds_of_continuous_viewing(agent):
    result = _run_node(CLOCK + MODULE + """
const C = window.LabTerminalCompletion, s = session(AGENT);
assert(C.getDelaySeconds() === 20, 'default delay');
show('vault1', s);
assert(C.meta('vault1', s), 'opening does not clear');
advance(19999);
assert(C.meta('vault1', s), '19.999 seconds is insufficient');
leave();
advance(10000);
show('vault1', s);
advance(19999);
assert(C.meta('vault1', s), 'reopening starts from zero');
advance(1);
assert(C.meta('vault1', s) === null, 'exactly twenty continuous seconds clears');
assert(C.meta('vault2', s), 'other scope stays unread');
assert(C.meta('vault1', {...s, agent_session_id:'other'}), 'other conversation stays unread');
console.log(JSON.stringify({passed:true}));
""".replace('AGENT', repr(agent)))
    assert result['passed']


def test_new_response_and_new_tab_start_new_timers():
    result = _run_node(CLOCK + MODULE + r"""
const C = window.LabTerminalCompletion, first = session(), second = session('claude', 100, 'two');
show('vault', first); advance(19000);
show('vault', second); advance(1000);
assert(C.meta('vault', first) && C.meta('vault', second), 'switch does not acknowledge either');
advance(19000);
assert(C.meta('vault', second) === null, 'second receives its full interval');
show('vault', first); advance(19000);
first.agent_activity = {...first.agent_activity, completed_at:200, completion_id:'turn2'};
termRenderSessionList(); advance(1000);
assert(C.meta('vault', first), 'new response is not consumed by previous response timer');
advance(19000);
assert(C.meta('vault', first) === null, 'new response clears after its own interval');
const running = {...first, name:'running', agent_session_id:'running', agent_activity:{state:'working'}};
show('vault', running); advance(60000);
running.agent_activity = {state:'completed', completed_at:300, completion_id:'turn3'};
termRenderSessionList();
assert(C.meta('vault', running), 'time before completion never counts');
advance(20000);
assert(C.meta('vault', running) === null, 'response viewed for full duration');
console.log(JSON.stringify({passed:true}));
""")
    assert result['passed']


@pytest.mark.parametrize('event', ['blur', 'visibilitychange', 'pagehide'])
def test_leaving_lab_resets_the_viewing_interval(event):
    result = _run_node(CLOCK + MODULE + """
const C = window.LabTerminalCompletion, s = session();
show('vault', s); advance(19000);
const event = EVENT;
if (event === 'visibilitychange') {document.hidden = true; documentEvents[event]();}
else {focused = false; windowEvents[event]();}
advance(30000);
assert(C.meta('vault', s), 'background time never acknowledges');
focused = true; document.hidden = false; windowEvents.focus();
advance(19999); assert(C.meta('vault', s), 'return needs another full interval');
advance(1); assert(C.meta('vault', s) === null, 'foreground full interval acknowledges');
console.log(JSON.stringify({passed:true}));
""".replace('EVENT', repr(event)))
    assert result['passed']


def test_delay_is_configurable_validated_and_persisted():
    result = _run_node(CLOCK + MODULE + r"""
let C = window.LabTerminalCompletion;
const s = session();
C.setDelaySeconds(5); show('vault', s);
advance(4999); assert(C.meta('vault', s), 'custom delay not reached');
advance(1); assert(C.meta('vault', s) === null, 'custom delay honored');
leave();
""" + MODULE + r"""
C = window.LabTerminalCompletion;
assert(C.getDelaySeconds() === 5, 'setting survives module reload');
assert(C.meta('vault', s) === null, 'acknowledgement survives reload');
C.setDelaySeconds(0); assert(C.getDelaySeconds() === 20, 'no invalid zero delay');
C.setDelaySeconds('invalid'); assert(C.getDelaySeconds() === 20, 'invalid uses default');
C.setDelaySeconds(3601); assert(C.getDelaySeconds() === 20, 'bounded delay');
const next = session('codex', 200); show('vault', next); advance(19000);
C.setDelaySeconds(30); advance(20000);
assert(C.meta('vault', next), 'changing delay restarts the interval');
advance(10000); assert(C.meta('vault', next) === null, 'changed delay honored');
console.log(JSON.stringify({passed:true}));
""")
    assert result['passed']


def test_confirmed_unread_survives_unknown_state_and_reload():
    result = _run_node(CLOCK + MODULE + r"""
let C = window.LabTerminalCompletion;
const s = session();
assert(C.meta('vault', s), 'confirmed completion');
s.agent_activity = {state:'unknown'};
assert(C.meta('vault', s), 'temporary unknown preserves completion');
assert(C.meta('vault', {...s, agent_session_id:'unverified'}) === null, 'unknown cannot create completion');
show('vault', s); advance(10000); leave();
""" + MODULE + r"""
C = window.LabTerminalCompletion;
assert(C.meta('vault', s), 'unread persists');
show('vault', s); advance(10000); assert(C.meta('vault', s), 'partial viewing not persisted');
advance(10000); assert(C.meta('vault', s) === null, 'confirmed completion acknowledged');
console.log(JSON.stringify({passed:true}));
""")
    assert result['passed']


def test_another_windows_new_response_cannot_be_acknowledged_by_an_old_timer():
    result = _run_node(CLOCK + MODULE + r"""
const C = window.LabTerminalCompletion, s = session();
show('vault', s); advance(19000);
const stored = JSON.parse(values['labTerminalCompletionsSeen-v1']);
Object.values(stored)[0].completed.at = 200;
values['labTerminalCompletionsSeen-v1'] = JSON.stringify(stored);
// Another window writes before this window receives its storage event.
advance(1000);
assert(C.meta('vault', s), 'older viewing timer must not acknowledge newer completion');
termRenderSessionList(); advance(20000);
assert(C.meta('vault', s) === null, 'new completion gets a full interval');
console.log(JSON.stringify({passed:true}));
""")
    assert result['passed']


def test_click_does_not_acknowledge_before_navigation_or_connection():
    activate = _js_between('  let _termTabActivationSeq =', '  function _termHomeAssociationHtml(session)')
    result = _run_node(CLOCK + MODULE + r"""
const s = session(), termSessions = [s];
const termCurrentSession = null, termCurrentWorkspaceId = null;
const _termActiveWorkspaceId=()=> '__self__', _termRecentScopeKey=()=> 'home';
const _termHomeAssociation=()=> 'logs', _termHomeSection=()=> 'home';
const _termRememberLast=()=>{};
const goToProductivity=()=>new Promise(()=>{});
""" + activate + r"""
void _termActivateTab('one'); advance(60000);
assert(window.LabTerminalCompletion.meta('home',s), 'click and pending navigation never mark seen');
console.log(JSON.stringify({passed:true}));
""")
    assert result['passed']


def test_only_visible_connected_terminal_can_start_or_continue_viewing():
    helper = _js_between('  function _termMarkVisibleCompletionSeen()', '  function termRenderSessionList()')
    result = _run_node(r"""
let calls = 0, stopped = 0, focus = true, rects = [{}];
const classes = new Set(['term-open']);
const document = {hidden:false, hasFocus:()=>focus, body:{classList:{contains:x=>classes.has(x)}}};
const WebSocket = {OPEN:1};
let termWS={readyState:1}, termXterm={}, termContainer={getClientRects:()=>rects};
let termCurrentWorkspaceId='workspace', termCurrentSession='one';
const _termActiveWorkspaceId=()=> 'workspace', _termRecentScopeKey=()=> 'vault::workspace';
const termSessions=[{name:'one'}];
window.LabTerminalCompletion={watch:()=> calls++, stopViewing:()=> stopped++};
""" + helper + r"""
_termMarkVisibleCompletionSeen();
focus=false; _termMarkVisibleCompletionSeen(); focus=true;
document.hidden=true; _termMarkVisibleCompletionSeen(); document.hidden=false;
classes.add('term-collapsed'); _termMarkVisibleCompletionSeen(); classes.delete('term-collapsed');
termWS.readyState=0; _termMarkVisibleCompletionSeen(); termWS.readyState=1;
rects=[]; _termMarkVisibleCompletionSeen(); rects=[{}];
termCurrentWorkspaceId='other'; _termMarkVisibleCompletionSeen(); termCurrentWorkspaceId='workspace';
_termMarkVisibleCompletionSeen();
console.log(JSON.stringify({tracked:calls===2,reset:stopped===6}));
""")
    assert all(result.values()), result
