"""Agent reports and submitted input drive status; green requires a review click."""
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
assert(C.details(s).reviewed&&C.details(s).reason==='reviewed-by-click'&&C.details(s).reviewed_at,'review stays inspectable after the dot clears');
''' + MODULE + r'''
C=window.LabTerminalCompletion;
assert(!C.status(s),'review survives reload');
assert(C.details(s).reviewed,'diagnostic review survives reload');
s.terminal_status=report('finished',2);
assert(C.meta('workspace',s),'later finish is a new green event');
assert(!C.details(s).reviewed&&!C.details(s).reviewed_at,'later report clears old review metadata');
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
assert(!C.acknowledge('workspace',s,'event-1'),'click on an older rendered dot cannot clear the current report');
assert(!C.acknowledge('workspace',s,null),'click on a tab without a rendered green cannot clear the current report');
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
assert(JSON.parse(_termSessionTooltipPayload(s)).completion.includes('Reviewed by click'),'cleared green remains explained on hover');
console.log(JSON.stringify({passed:true}));
''')
    assert result['passed']


def test_diagnostics_distinguish_stale_browser_missing_dot_and_review_without_mutation():
    app = (ROOT / 'core/src/core/static/js/lab-app.js').read_text()
    action = app.split("      'terminal-status':", 1)[1].split("      'terminal-notifications':", 1)[0].rstrip().removesuffix(',')
    result = _run_node(CLOCK + MODULE + r'''
const s=session('finished'),termSessions=[s];s.logical_name='codex';
const _termActiveWorkspaceId=()=> 'demo',_termVaultId=()=> 'owned',_vaultQuery=v=>'&vault='+v;
let server={...s,terminal_status:report('working',2)},dot=null;
document.querySelectorAll=()=>[{dataset:{name:s.name},querySelector:()=>dot}];
const getComputedStyle=()=>({visibility:'visible',backgroundColor:'green',animationName:'term-completion-blink'});
const fetch=async url=>{assert(url.includes('workspace_id=demo&vault=owned'),'diagnostics use captured scope');return {ok:true,json:async()=>[server]};};
const diagnose=''' + action + r''';
(async()=>{
 let result=await diagnose({name:'codex'}),row=result.sessions[0];
 assert(row.server_report.state==='working'&&row.browser_report.state==='finished'&&!row.in_sync,'stale browser is explicit');
 assert(row.indicator==='finished'&&!row.rendered.state&&!row.reviewed,'missing rendered dot is distinct from review');
 assert(window.LabTerminalCompletion.meta('demo',s),'diagnosing does not review');
 dot={classList:{contains:c=>c==='sess-completion'},getClientRects:()=>[{}]};
 server=s;row=(await diagnose({})).sessions[0];
 assert(row.in_sync&&row.rendered.visible&&row.rendered.state==='finished','current rendered finish is reported');
 assert(window.LabTerminalCompletion.acknowledge('demo',s),'explicit click reviews');
 dot=null;row=(await diagnose({})).sessions[0];
 assert(row.in_sync&&row.report.state==='finished'&&row.reviewed_at&&row.reason==='reviewed-by-click'&&!row.indicator,'review reason retained with authoritative report');
 console.log(JSON.stringify({passed:true}));
})();
''')
    assert result['passed']


def test_llm_submission_is_immediate_survives_stale_refresh_and_yields_to_agent():
    result = _run_node(CLOCK + MODULE + r'''
const C=window.LabTerminalCompletion,s={...session('attention'),llm_controlled:true};
C.input(s,'yes, ship it');
assert(C.status(s).state==='attention','drafts do not resume work');
C.input(s,'\r');
assert(C.status(s).label==='Working - responded yes, ship it','response is immediate yellow');
assert(C.details(s).reason==='user-submission'&&C.details(s).report.state==='attention','keep authoritative report inspectable');
assert(!C.acknowledge('workspace',s),'yellow cannot be reviewed');
assert(C.status({...s,terminal_status:null}).state==='working','missing/stale polls cannot restore red');
''' + MODULE + r'''
const D=window.LabTerminalCompletion;
assert(D.status(s).label==='Working - responded yes, ship it','pending survives reload');
s.terminal_status=report('working',2,'Deploying the change');
assert(D.status(s).label==='Working · Deploying the change'&&!D.details(s).pending,'agent supplies actual work');
s.terminal_status=report('finished',3);
assert(D.status(s).state==='finished','agent can finish normally');
D.input(s,'another job\r');
assert(D.status(s).label==='Working - submitted another job','new work replaces green immediately');
assert(!D.acknowledge('workspace',s,'event-3'),'old green click cannot clear pending submission');
assert(D.status({...s,llm_controlled:false}).state==='finished','opting out removes temporary feedback');
assert(D.status(s).state==='finished','re-enabling does not replay old submissions');
s.terminal_status=report('attention',4,'Choose a branch');
assert(D.status(s).state==='attention','next report replaces pending even if it needs more input');
console.log(JSON.stringify({passed:true}));
''')
    assert result['passed']


def test_llm_input_paste_edits_protocol_shells_and_control_markers():
    result = _run_node(CLOCK + MODULE + r'''
const C=window.LabTerminalCompletion;
const shell={name:'shell',created:1};C.input(shell,'echo hi\r');
assert(!C.status(shell),'ordinary shell submission has no effect');
const off={...shell,agent:'codex',llm_controlled:false};C.input(off,'test\r');
assert(!C.status(off),'explicit off overrides launch identity');
const s={name:'agent',created:1,agent:'codex'};
C.input(s,'\x1b[I\x1b[<64;10;10M\x1b[12;9R\x1b[?1;2c\r');
assert(!C.status(s),'focus/mouse/terminal replies and empty enter do not start work');
C.input(s,'\x1b[20');C.input(s,'0~first\r\nsecond');C.input(s,'\x1b[201~');
assert(!C.status(s),'multiline paste is a draft');
C.input(s,'\r');
assert(C.status(s).label==='Working - submitted first second','enter after paste submits');
s.terminal_status=report('attention',1);
C.input(s,'yex\x7fs\x1b[D!\x1b[C\r');
assert(C.status(s).label==='Working - responded ye!s','preview follows backspace and caret');
s.terminal_status=report('attention',2);
C.input(s,'\x1b[A\r');
assert(C.status(s).label==='Working - responded','history uses generic text instead of guessing');
s.terminal_status=report('attention',3);
C.input(s,'/clear\r');assert(C.status(s).state==='attention','local clear is not agent work');
C.input(s,'draft\x03');C.input(s,'\r');
assert(C.status(s).label==='Working - responded','enter accepts an attention prompt without inventing text');
assert(!C.status({...s,tmux_id:'$new',terminal_status:null}),'another incarnation cannot inherit pending input');
console.log(JSON.stringify({passed:true}));
''')
    assert result['passed']
