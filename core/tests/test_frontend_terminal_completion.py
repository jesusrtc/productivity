import pytest

from .test_frontend_terminal_ui import _run_node, _js_between, ROOT


def test_completion_acknowledgement_persists_and_is_conversation_scoped():
    script = (ROOT / 'core/src/core/static/js/lib/terminal-completion.js').read_text()
    result = _run_node('''
const values = {};
const localStorage = {getItem: key => values[key], setItem: (key, value) => values[key] = value};
window.addEventListener = () => {};
const document = {addEventListener() {}};
''' + script + '''
const session = {name:'terminal', agent:'codex', agent_session_id:'thread1', created_at:1,
  agent_activity:{state:'completed', completed_at:100, completion_id:'turn1'}};
const C = window.LabTerminalCompletion;
const unread = !!C.meta('vault1', session);
C.meta('vault1', session); // Hover/render does not acknowledge.
const stillUnread = !!C.meta('vault1', session);
C.see('vault1', session);
const read = C.meta('vault1', session) === null;
const otherVault = !!C.meta('vault2', session);
const otherThread = !!C.meta('vault1', {...session, agent_session_id:'thread2'});
const running = {...session, agent_activity:{state:'working'}};
const cannotReadFuture = !C.see('vault1', running);
const next = {...session, agent_activity:{state:'completed', completed_at:200, completion_id:'turn2'}};
const nextUnread = !!C.meta('vault1', next);
const unknown = C.meta('vault1', {...session, agent_session_id:'unverified', agent_activity:{state:'unknown'}}) === null;
const unknownRetainsConfirmed = !!C.meta('vault1', {...next, agent_activity:{state:'unknown'}});
C.see('vault1', next);
const staleDoesNotReturn = C.meta('vault1', session) === null;
''' + script + '''
const reloadRead = window.LabTerminalCompletion.meta('vault1', session) === null;
console.log(JSON.stringify({unread, stillUnread, read, otherVault, otherThread,
  cannotReadFuture, nextUnread, unknown, unknownRetainsConfirmed, staleDoesNotReturn, reloadRead}));
''')
    assert all(result.values()), result


@pytest.mark.parametrize('agent', ['codex', 'claude', 'copilot'])
def test_click_clears_before_navigation_or_attachment_finishes(agent):
    module = (ROOT / 'core/src/core/static/js/lib/terminal-completion.js').read_text()
    activate = _js_between('  let _termTabActivationSeq =', '  function _termHomeAssociationHtml(session)')
    result = _run_node('''
const values = {};
const localStorage = {getItem: key => values[key], setItem: (key, value) => values[key] = value};
window.addEventListener = () => {};
const document = {hidden:true, hasFocus:()=>false, addEventListener() {}};
''' + module + '''
const session={name:'one', logical_name:'one', agent:AGENT, agent_session_id:'thread1',
  agent_activity:{state:'completed', completed_at:100, completion_id:'turn1'}};
const termSessions=[session];
const _termActiveWorkspaceId=()=> '__self__', _termRecentScopeKey=()=> 'home';
const _termHomeAssociation=()=> 'logs', _termHomeSection=()=> 'home';
const _termRememberLast=()=>{};
let rendered=0, navigating=false;
const termRenderSessionList=()=> rendered++;
const goToProductivity=()=>{navigating=true; return new Promise(()=>{});};
'''.replace('AGENT', repr(agent)) + activate + '''
const C=window.LabTerminalCompletion;
const before=!!C.meta('home',session);
void _termActivateTab('one');
const immediate=C.meta('home',session)===null && rendered===1 && navigating;
session.agent_activity={state:'completed', completed_at:200, completion_id:'turn2'};
const nextUnread=!!C.meta('home',session);
console.log(JSON.stringify({before,immediate,nextUnread}));
''')
    assert all(result.values()), result


def test_only_a_visible_connected_terminal_in_the_focused_window_is_seen():
    helper = _js_between('  function _termMarkVisibleCompletionSeen()', '  function termRenderSessionList()')
    result = _run_node('''
let calls = 0, focus = true, rects = [{}];
const classes = new Set(['term-open']);
const document = {hidden:false, hasFocus:()=>focus, body:{classList:{contains:x=>classes.has(x)}}};
const WebSocket = {OPEN:1};
let termWS={readyState:1}, termXterm={}, termContainer={getClientRects:()=>rects};
let termCurrentWorkspaceId='workspace', termCurrentSession='one';
const _termActiveWorkspaceId=()=> 'workspace', _termRecentScopeKey=()=> 'vault::workspace';
const termSessions=[{name:'one'}];
window.LabTerminalCompletion={see:()=> calls++};
''' + helper + '''
_termMarkVisibleCompletionSeen();
const visible = calls === 1;
focus=false; _termMarkVisibleCompletionSeen(); focus=true;
document.hidden=true; _termMarkVisibleCompletionSeen(); document.hidden=false;
classes.add('term-collapsed'); _termMarkVisibleCompletionSeen(); classes.delete('term-collapsed');
termWS.readyState=0; _termMarkVisibleCompletionSeen(); termWS.readyState=1;
rects=[]; _termMarkVisibleCompletionSeen(); rects=[{}];
termCurrentWorkspaceId='other'; _termMarkVisibleCompletionSeen(); termCurrentWorkspaceId='workspace';
const preserved = calls === 1;
_termMarkVisibleCompletionSeen();
console.log(JSON.stringify({visible, preserved, reopening: calls === 2}));
''')
    assert all(result.values()), result
