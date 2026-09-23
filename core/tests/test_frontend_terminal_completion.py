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
assert(C.meta('vault2', s) === null, 'same shared terminal is acknowledged in every scope');
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


@pytest.mark.parametrize('agent', ['codex', 'claude', 'copilot'])
def test_double_click_acknowledges_without_a_viewing_delay(agent):
    result = _run_node(CLOCK + MODULE + """
const C = window.LabTerminalCompletion, s = session(AGENT);
show('vault', s);
advance(100);
assert(C.doubleClick('vault', s), 'double-click clears the exact unread response');
assert(C.meta('vault', s) === null, 'double-click clears immediately');
assert(!C.doubleClick('vault', s), 'no pending response leaves Rename available');
const running = {...s, name:'running', agent_session_id:'running', agent_activity:{state:'working'}};
assert(!C.doubleClick('vault', running), 'clicking during work cannot acknowledge a future response');
running.agent_activity = session(AGENT, 200).agent_activity;
assert(C.meta('vault', running), 'new completion still unread');
console.log(JSON.stringify({passed:true}));
""".replace('AGENT', repr(agent)))
    assert result['passed']


def test_double_click_cannot_acknowledge_an_unseen_newer_response_from_another_window():
    result = _run_node(CLOCK + MODULE + r"""
const C = window.LabTerminalCompletion, s = session();
show('vault', s);
const stored = JSON.parse(values['labTerminalCompletionsSeen-v1']);
Object.values(stored)[0].completed.at = 200;
values['labTerminalCompletionsSeen-v1'] = JSON.stringify(stored);
assert(!C.doubleClick('vault', s), 'only the displayed response can be dismissed');
assert(C.meta('vault', s), 'newer response stays unread');
console.log(JSON.stringify({passed:true}));
""")
    assert result['passed']


def test_new_work_cannot_hide_or_acknowledge_an_unread_response():
    result = _run_node(CLOCK + MODULE + r"""
const C = window.LabTerminalCompletion, s = session();
show('vault', s); advance(19000);
s.agent_activity = {state:'working'}; termRenderSessionList();
advance(60000);
assert(C.meta('vault', s), 'working time never consumes the older green dot');
assert(C.isWorking({...s, agent_activity:session().agent_activity}), 'a stale completed row cannot clear newer work');
s.agent_activity = {state:'unknown'}; termRenderSessionList(); advance(60000);
assert(C.isWorking(s) && C.meta('vault', s), 'missing state preserves both signals');
s.agent_activity = session('codex', 200).agent_activity;
termRenderSessionList(); advance(19999);
assert(C.meta('vault', s), 'new response receives its whole viewing interval');
advance(1); assert(C.meta('vault', s) === null, 'only full viewing clears');
console.log(JSON.stringify({passed:true}));
""")
    assert result['passed']


def test_out_of_order_shared_views_cannot_replay_old_work_or_completion():
    result = _run_node(CLOCK + MODULE + r"""
const C = window.LabTerminalCompletion, s = session();
const done = {...s, agent_activity:{...s.agent_activity, updated_at:100}};
const running = {...s, agent_activity:{state:'working', updated_at:200}};
const next = {...s, agent_activity:{...s.agent_activity, completed_at:300, updated_at:300}};
assert(!C.isWorking(done), 'first response finished');
assert(C.isWorking(running), 'new work starts');
assert(C.isWorking(done), 'stale completed poll cannot stop new work');
assert(!C.isWorking(next), 'new response stops working');
assert(!C.isWorking(running), 'stale working poll cannot revive completed work');
assert(!C.isWorking(next), 'latest response remains stopped');
const tied = {...s, name:'tied', agent_activity:{state:'working', updated_at:300}};
assert(C.isWorking(tied), 'start tie fixture');
tied.agent_activity = next.agent_activity;
assert(!C.isWorking(tied), 'completion at the same recorded millisecond still finishes');
console.log(JSON.stringify({passed:true}));
""")
    assert result['passed']


@pytest.mark.parametrize('agent', ['codex', 'claude', 'copilot'])
def test_working_survives_uncertain_reads_missing_identity_and_reload(agent):
    result = _run_node(CLOCK + MODULE + """
let C = window.LabTerminalCompletion;
const s = session(AGENT); s.agent_activity = {state:'working'};
assert(C.isWorking(s), 'verified working state');
for (const state of ['waiting', 'unknown', undefined]) {
  s.agent_activity = state ? {state} : undefined;
  assert(C.isWorking(s), 'waiting and uncertain state cannot erase working');
}
delete s.agent_session_id;
assert(C.isWorking(s), 'temporary missing live identity cannot erase working');
""".replace('AGENT', repr(agent)) + MODULE + r"""
C = window.LabTerminalCompletion;
assert(C.isWorking(s), 'working persists across reload');
assert(!C.isWorking({...s, created_at:2}), 'a different terminal incarnation does not inherit working');
assert(!C.isWorking({...s, name:'unseen'}), 'unknown alone never creates working');
s.agent_session_id='thread-one'; s.agent_activity=session(s.agent).agent_activity;
assert(!C.isWorking(s) && C.meta('vault', s), 'verified finish replaces yellow with green');
delete s.agent_session_id; s.agent_activity={state:'unknown'};
assert(C.meta('vault', s), 'identity gaps also preserve unread green');
assert(C.doubleClick('vault', s), 'known completion can still be acknowledged during identity gap');
s.agent_session_id='different-conversation';
assert(!C.isWorking(s) && !C.meta('vault', s), 'new verified conversation starts independently');
console.log(JSON.stringify({passed:true}));
""")
    assert result['passed']


def test_working_and_unread_completion_remain_visible_independently():
    helpers = _js_between('  function _termSessionDisplay(s)', '  function _termMarkVisibleCompletionSeen()')
    result = _run_node(CLOCK + MODULE + r"""
const termDeadSessions = new Set();
const termCurrentSession = null, termCurrentWorkspaceId = 'demo';
const _termActiveWorkspaceId = () => 'demo', _termRecentScopeKey = () => 'vault';
const _termSessionRecentMeta = () => ({label:'now'}), _termRecentWindowLabel = () => '5m';
const termSessEsc = value => String(value);
""" + helpers + r"""
const s = session();
const render = () => _termSessionPillHtml(s, 0);
const done = s.agent_activity;
s.agent_activity = {state:'working'};
assert(render().includes('sess-working') && !render().includes('sess-completion'), 'one yellow working dot');
s.agent_activity = done;
assert(render().includes('sess-completion') && !render().includes('sess-working'), 'one green completed dot');
assert(!render().includes('completion-ready'), 'completion never decorates the vertical line');
s.agent_activity = {state:'working'};
assert(render().includes('sess-working') && render().includes('sess-completion'), 'new work cannot hide an unread green dot');
assert(JSON.parse(_termSessionTooltipPayload(s)).completion, 'hover still describes the unread response');
termDeadSessions.add(s.name);
assert(render().includes('sess-working') && render().includes('sess-completion'), 'connection loss cannot erase either signal');
termDeadSessions.clear();
s.agent_activity = session('codex', 200).agent_activity;
show('vault', s); advance(19999);
assert(render().includes('sess-completion'), 'green remains during viewing delay');
advance(1);
assert(!render().includes('sess-activity'), 'green disappears after full viewing delay');
assert(render().includes(' recent'), 'recency stays independent after acknowledgement');
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
