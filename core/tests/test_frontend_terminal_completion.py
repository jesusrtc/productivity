import json

import pytest

from core import agent_activity

from .test_frontend_terminal_ui import _run_node, _js_between, ROOT
from .test_agent_activity import copilot_autopilot_events, copilot_cli_events, write_events


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
  if (view) window.LabTerminalCompletion.meta(view.scope, view.session);
}
function show(scope, session) {view = {scope, session}; termRenderSessionList();}
function leave() {view = null;}
function session(agent = 'codex', completed_at = 100, name = 'one') {
  return {name, agent, agent_session_id:'thread-'+name, created_at:1,
    agent_activity:{state:'completed', completed_at, completion_id:'turn-'+completed_at}};
}
const assert = (ok, message) => {if (!ok) throw Error(message);};
"""


def test_native_copilot_autopilot_changes_yellow_to_unread_green():
    events = copilot_autopilot_events()
    working = agent_activity.response_state('copilot', events[:4], include_timestamp=True)
    completed = agent_activity.response_state('copilot', events, include_timestamp=True)
    result = _run_node(CLOCK + MODULE + """
const C = window.LabTerminalCompletion, s = session('copilot');
s.agent_activity = WORKING;
show('workspace', s);
assert(C.isWorking(s) && !C.meta('workspace', s), 'tool execution stays yellow');
s.agent_activity = COMPLETED;
termRenderSessionList();
assert(!C.isWorking(s) && C.meta('workspace', s), 'accepted completion replaces yellow with green');
advance(19999);
assert(C.meta('workspace', s), 'green remains unread while selected');
advance(1);
assert(C.meta('workspace', s), 'twenty seconds cannot acknowledge green');
assert(C.acknowledge('workspace',s) && !C.meta('workspace',s), 'explicit review clears green');
console.log(JSON.stringify({passed:true}));
""".replace('WORKING', json.dumps(working)).replace('COMPLETED', json.dumps(completed)))
    assert result['passed']


@pytest.mark.parametrize('agent', ['codex', 'claude', 'copilot'])
def test_selected_terminal_never_acknowledges_without_explicit_review(agent):
    result = _run_node(CLOCK + MODULE + """
const C = window.LabTerminalCompletion, s = session(AGENT);
show('vault1', s);
assert(C.meta('vault1', s), 'opening does not clear');
advance(19999);
assert(C.meta('vault1', s), 'selected viewing never reviews the result');
leave();
advance(10000);
show('vault1', s);
advance(19999);
assert(C.meta('vault1', s), 'reopening cannot acknowledge the result');
advance(1);
assert(C.meta('vault1', s), 'twenty continuous seconds cannot clear green');
advance(3600000);termRenderSessionList();
assert(C.meta('vault1',s) && timers.size===0, 'even an hour selected leaves green pending without an acknowledgement timer');
assert(C.acknowledge('vault1',s), 'explicit review acknowledges immediately');
assert(C.meta('vault2', s) === null, 'same shared terminal is acknowledged in every scope');
assert(C.meta('vault1', {...s, agent_session_id:'other'}), 'other conversation stays unread');
console.log(JSON.stringify({passed:true}));
""".replace('AGENT', repr(agent)))
    assert result['passed']


def test_selection_and_new_responses_require_their_own_explicit_review():
    result = _run_node(CLOCK + MODULE + r"""
const C = window.LabTerminalCompletion, first = session(), second = session('claude', 100, 'two');
show('vault', first); advance(19000);
show('vault', second); advance(1000);
assert(C.meta('vault', first) && C.meta('vault', second), 'switch does not acknowledge either');
advance(19000);
assert(C.meta('vault', second), 'second remains unread while selected');
assert(C.acknowledge('vault',second), 'reviewing one terminal is explicit');
show('vault', first); advance(19000);
first.agent_activity = {...first.agent_activity, completed_at:200, completion_id:'turn2'};
termRenderSessionList(); advance(1000);
assert(C.meta('vault', first), 'new response cannot be consumed by prior selection');
advance(19000);
assert(C.meta('vault', first), 'new response remains unread after twenty seconds');
assert(C.acknowledge('vault',first), 'only explicit review clears the new response');
const running = {...first, name:'running', agent_session_id:'running', agent_activity:{state:'working'}};
show('vault', running); advance(60000);
running.agent_activity = {state:'completed', completed_at:300, completion_id:'turn3'};
termRenderSessionList();
assert(C.meta('vault', running), 'time before completion never counts');
advance(20000);
assert(C.meta('vault', running), 'a response finishing in the active terminal keeps blinking');
assert(C.acknowledge('vault',running), 'reviewing the active terminal clears it');
console.log(JSON.stringify({passed:true}));
""")
    assert result['passed']


@pytest.mark.parametrize('agent', ['codex', 'claude', 'copilot', None])
def test_output_changes_drive_yellow_then_green_after_forty_quiet_seconds(agent):
    result = _run_node(CLOCK + "Date.now = () => 1000000 + clock;\n" + MODULE + r"""
const C = window.LabTerminalCompletion, s = {name:'output',created:900,agent:AGENT,
  output_activity:{updated_at:1000,observed_at:1000}};
show('workspace', s);
assert(C.isWorking(s) && !C.meta('workspace',s), 'all terminal types show yellow on recent output without needing a provider identity');
advance(39999);termRenderSessionList();
assert(C.isWorking(s) && !C.meta('workspace',s), '39.999 quiet seconds are still WIP');
advance(1);termRenderSessionList();
assert(!C.isWorking(s) && C.meta('workspace',s).label.includes('Output quiet for 40 seconds'), '40 seconds produces a ready-to-review signal');
advance(19999);assert(C.meta('workspace',s), 'the earlier active working time cannot dismiss green');
advance(1);assert(C.meta('workspace',s), 'twenty active seconds do not acknowledge green');
assert(C.acknowledge('workspace',s), 'explicit tab or green review acknowledges immediately');
s.output_activity={updated_at:1060,observed_at:1060};termRenderSessionList();
assert(C.isWorking(s) && !C.meta('workspace',s), 'new output creates yellow after the previous result was reviewed');
advance(40000);termRenderSessionList();
assert(C.meta('workspace',s) && C.acknowledge('workspace',s), 'the next quiet result can be dismissed directly');
assert(!C.meta('other-workspace',s) && !C.isWorking(s), 'direct acknowledgement is shared across views');
console.log(JSON.stringify({passed:true}));
""".replace('AGENT', json.dumps(agent)))
    assert result['passed']


def test_output_activity_handles_clock_offset_stale_views_identity_gaps_and_reload():
    result = _run_node(CLOCK + "Date.now = () => 1000000 + clock;\n" + MODULE + r"""
let C = window.LabTerminalCompletion;
const s={name:'output',created:4900,agent:'codex',agent_session_id:'thread-one',
  agent_activity:{state:'working'},output_activity:{updated_at:5000,observed_at:5000}};
assert(C.isWorking(s), 'server clock ahead of browser still starts yellow');
advance(40000);
const quiet={...s,output_activity:{updated_at:5000,observed_at:5040}};
assert(!C.isWorking(quiet) && C.meta('workspace',quiet), 'server clock offset does not prevent the quiet result');
const stale={...s,output_activity:{updated_at:5000,observed_at:5001}};
assert(!C.isWorking(stale), 'an old shared view cannot replay yellow after quiet');
const newer={...s,agent_session_id:'thread-two',output_activity:{updated_at:5040,observed_at:5040}};
assert(C.isWorking(newer), 'new content is WIP even if a previous transcript remains working');
assert(C.isWorking(quiet), 'stale content cannot stop newer work');
const gap={...newer,output_activity:undefined,agent_session_id:undefined,agent_activity:{state:'unknown'}};
assert(C.isWorking(gap), 'a missing timestamp retains the last known activity rather than inventing a finish');
leave();
""" + MODULE + r"""
C=window.LabTerminalCompletion;
assert(C.isWorking(gap), 'known output activity survives reload and identity gaps');
newer.output_activity={updated_at:5040,observed_at:5080};
assert(!C.isWorking(newer) && C.meta('workspace',newer), 'the next actual observation finishes the quiet period');
assert(C.acknowledge('workspace',newer), 'direct review works after reload');
assert(!C.meta('other', {...newer,agent_session_id:'thread-three'}), 'provider mapping changes cannot resurrect reviewed output');
assert(!C.meta('workspace',{...newer,created:4901,output_activity:undefined}), 'other terminal incarnations do not inherit an output result');
const untouched={name:'never-active',created:5000,output_activity:{updated_at:5000,observed_at:5080}};
assert(!C.meta('workspace',untouched) && !C.meta('workspace',untouched), 'an idle creation baseline cannot create green on repeated renders');
untouched.output_activity={updated_at:5081,observed_at:5121};
assert(C.meta('workspace',untouched), 'later actual output can produce green even when observed after its quiet period');
console.log(JSON.stringify({passed:true}));
""")
    assert result['passed']


def test_cloned_cached_output_samples_cannot_restart_the_quiet_period():
    result = _run_node(CLOCK + "Date.now = () => 1000000 + clock;\n" + MODULE + r"""
const C = window.LabTerminalCompletion;
const s = {name:'cached-output',created:900,output_activity:{updated_at:1000,observed_at:1000}};
assert(C.isWorking(s), 'fresh output starts yellow');
for (let i=0;i<4;i++) {
  advance(10000);
  s.output_activity={...s.output_activity};
  C.isWorking(s);
}
assert(!C.isWorking(s) && C.meta('workspace',s), 'recloning a cached sample does not extend its forty seconds');
s.output_activity={...s.output_activity};
assert(!C.isWorking(s), 'recloning after quiet cannot revive yellow');
assert(C.acknowledge('workspace',s), 'explicit review still clears green');
advance(10000);s.output_activity={...s.output_activity};
assert(!C.isWorking(s) && !C.meta('workspace',s), 'cached output cannot recreate a reviewed cycle');
s.output_activity={updated_at:1060,observed_at:1060};
assert(C.isWorking(s), 'a genuine newer output event starts the next cycle');
console.log(JSON.stringify({passed:true}));
""")
    assert result['passed']


def test_content_verification_migrates_false_raw_signals_and_preserves_real_review():
    result = _run_node(CLOCK + "Date.now = () => 1000000 + clock;\n" + MODULE + r"""
let C = window.LabTerminalCompletion;
const s = {name:'ssh',created:900,agent:'codex',agent_session_id:'thread',
  agent_activity:{state:'working'},output_activity:{updated_at:1000,observed_at:1040}};
assert(C.meta('workspace',s), 'the old raw I/O detector left a false unread result');
s.output_activity={version:2,generation:'content-one',updated_at:0,observed_at:1041};
assert(!C.isWorking(s) && !C.meta('workspace',s), 'the first verified screen is a baseline, clearing phantom raw I/O');
const old={...s,output_activity:{updated_at:1042,observed_at:1042}};
assert(!C.isWorking(old) && !C.meta('workspace',old), 'an old-format cached view cannot resurrect phantom activity');
s.output_activity={version:2,generation:'content-one',updated_at:1042,observed_at:1042};
assert(C.isWorking(s), 'verified content changes start yellow');
advance(40000);
assert(!C.isWorking(s) && C.meta('workspace',s), 'verified content still becomes ready to review');
s.output_activity={version:2,generation:'content-one',updated_at:1042,observed_at:1083};
assert(C.meta('workspace',s), 'noise with no content change retains the same unread result');
""" + MODULE + r"""
C=window.LabTerminalCompletion;
assert(C.meta('workspace',s), 'verified unread content survives a browser reload');
s.output_activity={version:2,generation:'after-server-restart',updated_at:0,observed_at:1084};
assert(!C.isWorking(s) && C.meta('workspace',s), 'a backend baseline cannot invent work or erase a verified unread result');
assert(C.acknowledge('workspace',s) && !C.meta('workspace',s), 'tab-click review is retained across a backend restart');
const stale={...s,output_activity:{version:2,generation:'content-one',updated_at:1042,observed_at:1083}};
assert(!C.isWorking(stale) && !C.meta('workspace',stale), 'an old generation cannot replay activity or completion');
s.output_activity={version:2,generation:'after-server-restart',updated_at:1085,observed_at:1085};
assert(C.isWorking(s) && !C.meta('workspace',s), 'only a new verified change creates the next signal');
console.log(JSON.stringify({passed:true}));
""")
    assert result['passed']


@pytest.mark.parametrize('agent', ['codex', 'claude', 'copilot'])
def test_direct_green_review_acknowledges_without_a_viewing_delay(agent):
    result = _run_node(CLOCK + MODULE + """
const C = window.LabTerminalCompletion, s = session(AGENT);
show('vault', s);
advance(100);
assert(C.acknowledge('vault', s), 'direct green review clears the exact unread response');
assert(C.meta('vault', s) === null, 'direct green review clears immediately');
assert(!C.acknowledge('vault', s), 'no pending response cannot be reviewed');
const running = {...s, name:'running', agent_session_id:'running', agent_activity:{state:'working'}};
assert(!C.acknowledge('vault', running), 'clicking during work cannot acknowledge a future response');
running.agent_activity = session(AGENT, 200).agent_activity;
assert(C.meta('vault', running), 'new completion still unread');
console.log(JSON.stringify({passed:true}));
""".replace('AGENT', repr(agent)))
    assert result['passed']


def test_direct_review_cannot_acknowledge_an_unseen_newer_response_from_another_window():
    result = _run_node(CLOCK + MODULE + r"""
const C = window.LabTerminalCompletion, s = session();
show('vault', s);
const stored = JSON.parse(values['labTerminalCompletionsSeen-v1']);
Object.values(stored)[0].completed.at = 200;
values['labTerminalCompletionsSeen-v1'] = JSON.stringify(stored);
assert(!C.acknowledge('vault', s), 'only the displayed response can be dismissed');
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
assert(C.meta('vault', s), 'new response remains unread while selected');
advance(1); assert(C.meta('vault', s), 'viewing cannot acknowledge it');
assert(C.acknowledge('vault',s), 'explicit review clears only the observed result');
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
assert(C.acknowledge('vault', s), 'known completion can still be acknowledged during identity gap');
s.agent_session_id='different-conversation';
assert(!C.isWorking(s) && !C.meta('vault', s), 'new verified conversation starts independently');
console.log(JSON.stringify({passed:true}));
""")
    assert result['passed']


def test_working_and_unread_completion_remain_visible_independently():
    helpers = _js_between('  function _termSessionDisplay(s)', '  function _termTaskPlaceholderHtml(')
    result = _run_node(CLOCK + MODULE + r"""
const termDeadSessions = new Set();
const termCurrentSession = null, termCurrentWorkspaceId = 'demo';
const _termActiveWorkspaceId = () => 'demo', _termRecentScopeKey = () => 'vault';
const _termSessionRecentMeta = () => ({label:'now'}), _termRecentWindowLabel = () => '5m';
const termSessEsc = value => String(value);
""" + helpers + r"""
const C=window.LabTerminalCompletion,s = session();
const render = () => _termSessionPillHtml(s, 0);
const done = s.agent_activity;
s.agent_activity = {state:'working'};
assert(render().includes('sess-working') && !render().includes('sess-completion'), 'one yellow working dot');
window.LabObjectives = {taskForTerminal:()=>({title:'Verify the fix',icon:'<svg class="ft-nb"></svg>',assetIcon:'<svg class="ft-nb"></svg>',status:'todo',inherited:false})};
assert(render().includes('<svg class="ft-nb">') && render().includes('Task: Verify the fix') && render().includes('sess-working'), 'a task-linked terminal inherits its asset icon and retains working status');
delete window.LabObjectives;
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
assert(render().includes('sess-completion'), 'green remains while selected');
advance(1);
assert(render().includes('sess-completion'), 'green remains after twenty active seconds');
assert(C.acknowledge('vault',s) && !render().includes('sess-activity'), 'explicit review clears green');
assert(render().includes(' recent'), 'recency stays independent after acknowledgement');
console.log(JSON.stringify({passed:true}));
""")
    assert result['passed']


@pytest.mark.parametrize('recording', ['tool-response', 'abrupt-resume'])
def test_recorded_copilot_cli_events_drive_terminal_dots(tmp_path, recording):
    events = copilot_cli_events(recording)
    path = tmp_path / 'events.jsonl'
    states = []
    for index in range(len(events)):
        write_events(path, events[:index + 1])
        states.append(agent_activity.read_activity('copilot', path))
    helpers = _js_between('  function _termSessionDisplay(s)', '  function _termTaskPlaceholderHtml(')
    result = _run_node(CLOCK + MODULE + r"""
const termDeadSessions = new Set();
const termCurrentSession = null, termCurrentWorkspaceId = 'demo';
const _termActiveWorkspaceId = () => 'demo', _termRecentScopeKey = () => 'vault::demo';
const _termSessionRecentMeta = () => null, _termRecentWindowLabel = () => '5m';
const termSessEsc = value => String(value);
""" + helpers + '\nconst states = ' + json.dumps(states) + r""";
const s = {...session('copilot'), kind:'claude'};
for (const state of states) {
  s.agent_activity = state;
  const html = _termSessionPillHtml(s, 0);
  const yellow = html.includes('sess-working'), green = html.includes('sess-completion');
  assert(yellow === ['working','waiting'].includes(state.state), 'native Copilot event sets the yellow terminal dot: '+JSON.stringify(state));
  assert(green === (state.state === 'completed'), 'only native final completion creates green: '+JSON.stringify(state));
}
const C = window.LabTerminalCompletion;
if (states.at(-1).state === 'completed') {
  s.agent_activity = {state:'working',updated_at:states.at(-1).updated_at+1};
  const html = _termSessionPillHtml(s, 0);
  assert(html.includes('sess-working') && html.includes('sess-completion'), 'a new Copilot request preserves unread green alongside yellow');
  assert(C.acknowledge('vault::demo',s), 'direct green review acknowledges the recorded final response');
  assert(C.isWorking(s) && !C.meta('vault::demo',s), 'review keeps the new Copilot work yellow');
} else {
  assert(!C.isWorking(s) && !C.meta('vault::demo',s), 'native idle resume clears retained yellow without inventing green');
}
console.log(JSON.stringify({passed:true}));
""")
    assert result['passed']


@pytest.mark.parametrize('event', ['blur', 'visibilitychange', 'pagehide'])
def test_focus_and_visibility_changes_never_acknowledge_a_result(event):
    result = _run_node(CLOCK + MODULE + """
const C = window.LabTerminalCompletion, s = session();
show('vault', s); advance(19000);
const event = EVENT;
if (event === 'visibilitychange') {document.hidden = true; documentEvents[event]();}
else {focused = false; windowEvents[event]?.();}
advance(30000);
assert(C.meta('vault', s), 'background time never acknowledges');
focused = true; document.hidden = false; windowEvents.focus();
advance(60000); assert(C.meta('vault', s), 'returning and remaining active cannot acknowledge green');
assert(C.acknowledge('vault',s), 'explicit review still acknowledges it');
console.log(JSON.stringify({passed:true}));
""".replace('EVENT', repr(event)))
    assert result['passed']


@pytest.mark.parametrize('legacy_delay', [1, 20, 3600])
def test_saved_automatic_delay_cannot_acknowledge_green(legacy_delay):
    result = _run_node(CLOCK + f"values['labTerminalCompletionReadSeconds']='{legacy_delay}';\n" + MODULE + r"""
let C = window.LabTerminalCompletion;
const s = session();
show('vault', s);advance(3600001);termRenderSessionList();
assert(C.meta('vault',s) && timers.size===0, 'saved legacy delay cannot create an automatic acknowledgement');
leave();
""" + MODULE + r"""
C = window.LabTerminalCompletion;
assert(C.meta('vault',s), 'reload preserves the unread result');
assert(C.acknowledge('vault',s), 'explicit review clears it immediately');
leave();
""" + MODULE + r"""
assert(!window.LabTerminalCompletion.meta('vault',s), 'explicit acknowledgement survives reload');
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
advance(3600000); assert(C.meta('vault', s), 'continued viewing does not acknowledge after reload');
assert(C.acknowledge('vault',s), 'explicit review acknowledges the retained result');
console.log(JSON.stringify({passed:true}));
""")
    assert result['passed']


def test_another_windows_new_response_cannot_be_acknowledged_by_elapsed_time():
    result = _run_node(CLOCK + MODULE + r"""
const C = window.LabTerminalCompletion, s = session();
show('vault', s); advance(19000);
const stored = JSON.parse(values['labTerminalCompletionsSeen-v1']);
Object.values(stored)[0].completed.at = 200;
values['labTerminalCompletionsSeen-v1'] = JSON.stringify(stored);
// Another window writes before this window receives its storage event.
advance(1000);
assert(C.meta('vault', s), 'elapsed time cannot acknowledge newer completion');
termRenderSessionList(); advance(20000);
assert(C.meta('vault', s), 'new completion remains unread');
assert(!C.acknowledge('vault',s), 'stale explicit review cannot dismiss another windows newer result');
console.log(JSON.stringify({passed:true}));
""")
    assert result['passed']


def test_programmatic_navigation_does_not_acknowledge_a_result():
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
assert(window.LabTerminalCompletion.meta('home',s), 'programmatic activation and pending navigation never mark seen');
console.log(JSON.stringify({passed:true}));
""")
    assert result['passed']


def test_hidden_or_unfocused_review_cannot_acknowledge_green():
    result = _run_node(CLOCK + MODULE + r"""
const C=window.LabTerminalCompletion,s=session();
assert(C.meta('vault',s), 'unread result');
document.hidden=true;assert(!C.acknowledge('vault',s), 'hidden review cannot acknowledge');
document.hidden=false;focused=false;assert(!C.acknowledge('vault',s), 'unfocused review cannot acknowledge');
focused=true;assert(C.meta('vault',s) && C.acknowledge('vault',s), 'focused explicit review clears it');
console.log(JSON.stringify({passed:true}));
""")
    assert result['passed']
