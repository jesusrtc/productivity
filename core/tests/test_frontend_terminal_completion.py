"""Agent reports alone drive status; only an explicit green click acknowledges."""
import pytest
from .test_frontend_terminal_ui import _run_node, ROOT

MODULE = (ROOT / 'core/src/core/static/js/lib/terminal-completion.js').read_text()
CLOCK = r'''
const values = {}, windowEvents = {}, documentEvents = {};
const localStorage = {getItem:key=>values[key],setItem:(key,value)=>values[key]=value};
let focused=true;
const document = {hidden:false,hasFocus:()=>focused,addEventListener:(event,fn)=>documentEvents[event]=fn};
window.addEventListener=(event,fn)=>windowEvents[event]=fn;
window.dispatchEvent=()=>{};
const assert=(ok,message)=>{if(!ok)throw Error(message)};
function report(state, revision=1, message='') {return {version:1,state,revision,id:'event-'+revision,updated_at:revision,message};}
function session(state, revision=1) {return {name:'one',created:100,tmux_socket:'owned',tmux_id:'$1',terminal_status:report(state,revision)};}
'''


@pytest.mark.parametrize('state', ['working', 'attention'])
def test_only_agent_can_change_working_and_attention(state):
    result = _run_node(CLOCK + MODULE + r'''
const C=window.LabTerminalCompletion, s=session(STATE);
assert(C.status(s).state===STATE,'report applies');
assert(!C.acknowledge('workspace',s),'tab/indicator clicks cannot clear this state');
s.agent_activity={state:'completed',completion_id:'guessed',completed_at:999999};
s.output_activity={updated_at:10,observed_at:999999};
Date.now=()=>9999999999999;
assert(C.status(s).state===STATE&&!C.meta('workspace',s),'silence and provider events never finish');
windowEvents.focus();documentEvents.visibilitychange();
assert(C.status(s).state===STATE,'focus is not a state change');
s.terminal_status=report('finished',2);
assert(C.meta('workspace',s)&&!C.isWorking(s),'only a new agent report finishes');
console.log(JSON.stringify({passed:true}));
'''.replace('STATE',repr(state)))
    assert result['passed']


def test_finished_requires_click_and_resets_across_shared_views_and_reload():
    result = _run_node(CLOCK + MODULE + r'''
let C=window.LabTerminalCompletion;const s=session('finished');
assert(C.meta('workspace',s)&&C.meta('document',s),'all views share unread green');
windowEvents.focus();documentEvents.visibilitychange();
assert(C.meta('workspace',s),'selection/focus/time do not clear');
focused=false;assert(!C.acknowledge('workspace',s),'background view cannot review');
focused=true;assert(C.acknowledge('workspace',s),'click acknowledges');
assert(!C.status(s)&&!C.meta('document',s),'tab status resets everywhere');
''' + MODULE + r'''
C=window.LabTerminalCompletion;
assert(!C.status(s),'review survives reload');
s.terminal_status=report('finished',2);
assert(C.meta('workspace',s),'later finish is a new green event');
assert(C.acknowledge('workspace',s)&&!C.status(s),'later click clears it');
console.log(JSON.stringify({passed:true}));
''')
    assert result['passed']


def test_stale_rows_and_clicks_cannot_override_new_report_or_acknowledge_future_finish():
    result = _run_node(CLOCK + MODULE + r'''
const C=window.LabTerminalCompletion, old=session('finished'), s=session('attention',2);
assert(C.meta('workspace',old),'initial green');
assert(C.status(s).state==='attention','new attention replaces old green');
assert(!C.acknowledge('workspace',old),'stale green cannot clear attention');
assert(C.status(old).state==='attention','stale reads cannot change attention');
const gap={...s,terminal_status:null};
assert(C.status(gap).state==='attention','missing observation retains last report');
s.terminal_status=report('working',3);
assert(C.isWorking(s)&&!C.meta('workspace',s),'agent can resume');
assert(!C.acknowledge('workspace',s),'working click cannot pre-acknowledge');
s.terminal_status=report('finished',4);
assert(C.meta('workspace',s),'finish after working click remains unread');
assert(!C.acknowledge('workspace',old),'stale old finish cannot acknowledge new finish');
console.log(JSON.stringify({passed:true}));
''')
    assert result['passed']


def test_identity_is_socket_and_session_incarnation_not_provider_or_view():
    result = _run_node(CLOCK + MODULE + r'''
const C=window.LabTerminalCompletion, s=session('finished');
assert(C.acknowledge('workspace',s),'finish acknowledged');
assert(!C.meta('document',{...s,agent:'copilot',agent_session_id:'new'}),'provider change does not replay green');
assert(C.meta('workspace',{...s,tmux_socket:'other'}),'other socket is independent');
assert(C.meta('workspace',{...s,tmux_id:'$2'}),'same-second recreation is independent');
assert(C.meta('workspace',{...s,created:101}),'restarted session is independent');
console.log(JSON.stringify({passed:true}));
''')
    assert result['passed']


def test_no_report_means_no_inferred_status_and_old_storage_is_ignored():
    result = _run_node(CLOCK + r'''
values['labTerminalActivity-v1']=JSON.stringify({old:{working:true}});
values['labTerminalCompletionsSeen-v1']=JSON.stringify({old:{completed:{at:999}}});
''' + MODULE + r'''
const C=window.LabTerminalCompletion;
const s={name:'old',created:100,agent:'codex',agent_session_id:'thread',
 agent_activity:{state:'completed',completed_at:999,completion_id:'done'},
 output_activity:{updated_at:10,observed_at:999999}};
assert(!C.status(s)&&!C.isWorking(s)&&!C.meta('workspace',s),'no inferred green or yellow');
s.agent_activity={state:'working'};
assert(!C.isWorking(s),'provider activity cannot set yellow either');
console.log(JSON.stringify({passed:true}));
''')
    assert result['passed']


def test_report_message_survives_reload_and_storage_events():
    result = _run_node(CLOCK + MODULE + r'''
const s=session('attention');s.terminal_status.message='Review the preview';
assert(window.LabTerminalCompletion.status(s).label==='Needs your attention · Review the preview','hover details');
''' + MODULE + r'''
const C=window.LabTerminalCompletion;
assert(C.status({...s,terminal_status:null}).state==='attention','report survives reload');
windowEvents.storage({key:'labTerminalReports-v1'});
assert(!C.acknowledge('workspace',s)&&C.status(s).state==='attention','storage events do not dismiss red');
console.log(JSON.stringify({passed:true}));
''')
    assert result['passed']


def test_terminal_renderer_has_one_reported_dot_and_escaped_hover_text():
    from .test_frontend_terminal_ui import _js_between
    helpers = _js_between('  function _termSessionDisplay(s)', '  function _termTaskPlaceholderHtml(')
    result = _run_node(CLOCK + MODULE + r'''
const termDeadSessions=new Set(),termCurrentSession=null,termCurrentWorkspaceId='demo';
const _termActiveWorkspaceId=()=> 'demo',_termRecentScopeKey=()=> 'workspace';
const _termSessionRecentMeta=()=>null;
const termSessEsc=value=>String(value).replaceAll('&','&amp;').replaceAll('"','&quot;').replaceAll('<','&lt;');
''' + helpers + r'''
const C=window.LabTerminalCompletion,s=session('working');
s.terminal_status.message='<literal> "quoted"';
let html=_termSessionPillHtml(s,0);
assert(html.includes('sess-working')&&!html.includes('sess-completion')&&!html.includes('sess-attention'),'one yellow dot');
assert(html.includes('&lt;literal>')&&!html.includes('<literal>'),'hover text is escaped');
s.terminal_status=report('attention',2,'Review preview');html=_termSessionPillHtml(s,0);
assert(html.includes('sess-attention')&&!html.includes('sess-working'),'red replaces yellow');
assert(JSON.parse(_termSessionTooltipPayload(s)).completion.includes('Review preview'),'hover carries status message');
assert(!C.acknowledge('workspace',s),'red stays on tab click');
s.terminal_status=report('finished',3);html=_termSessionPillHtml(s,0);
assert(html.includes('sess-completion')&&!html.includes('sess-attention'),'green replaces red');
assert(C.acknowledge('workspace',s)&&!_termSessionPillHtml(s,0).includes('sess-activity'),'green click clears status');
console.log(JSON.stringify({passed:true}));
''')
    assert result['passed']
