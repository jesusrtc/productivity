"""Terminal tab timing requires rendered text and owns every fixture session."""
import importlib.util
import io
import json

import pytest

from .test_frontend_terminal_ui import ROOT, _run_node


def test_terminal_tab_probe_requires_render_focus_scope_and_exact_input():
    source = (ROOT / 'scripts/perf/terminal_tab_probe.mjs').read_text()
    install = source[source.index('function install(fixtures)'):]
    result = _run_node(r'''
const window={};
let termCurrentSession='one',termCurrentWorkspaceId='alpha',termXterm=null;
const pane={getBoundingClientRect:()=>({width:100})},termContainer=pane;
const termWS={readyState:1},_termCache=new Map(),_termCacheKey=(s,n)=>s+'::'+n;
const input={},document={activeElement:input,querySelector:()=>({}),querySelectorAll:()=>[pane]};
let value='ready',listener;
function termEnsureXterm(){termXterm={
 element:{querySelector:()=>input},onRender:fn=>listener=fn,
 buffer:{active:{viewportY:0,baseY:0,cursorY:0,cursorX:20,getLine:()=>({translateToString:()=>value})}},
};}
''' + install + r'''
install([{name:'one',marker:'ready'},{name:'two',marker:'other'}]);
termEnsureXterm();const probe=window.__terminalTabs;
const checks=[];
checks.push(!probe.ready('one'));
listener({start:0,end:0});checks.push(probe.ready('one'));
probe.expectInput('one','a');value='readya';checks.push(!probe.ready('one'));
listener({start:1,end:2});checks.push(!probe.ready('one'));
listener({start:0,end:0});checks.push(probe.ready('one'));
value='readya!';checks.push(!probe.ready('one'));value='readya';
document.activeElement=null;checks.push(!probe.ready('one'));document.activeElement=input;
termCurrentWorkspaceId='beta';checks.push(!probe.ready('one'));termCurrentWorkspaceId='alpha';
termWS.readyState=3;checks.push(!probe.ready('one'));termWS.readyState=1;
checks.push(!probe.ready('two'));
termXterm=null;termEnsureXterm();checks.push(!probe.ready('one'));
listener({start:0,end:0});checks.push(probe.ready('one'));
const states=[probe.cacheState('one'),probe.cacheState('two')];
_termCache.set('alpha::two',{ws:{readyState:1}});states.push(probe.cacheState('two'));
_termCache.get('alpha::two').ws.readyState=3;states.push(probe.cacheState('two'));
console.log(JSON.stringify({checks,states,records:probe.snapshot().records.length}));
''')
    assert len(result['checks']) == 12 and all(result['checks'])
    assert result['states'] == ['mounted', 'cold', 'warm', 'stale']
    assert result['records'] == 2


def fixture_module():
    spec = importlib.util.spec_from_file_location('terminal_tab_fixture', ROOT / 'scripts/perf/terminal_tab_fixture.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('workspace', ['/', '/workspaces/alpha', '/tmp/user/vault/workspaces/alpha'])
def test_terminal_fixture_rejects_nonfixture_paths(workspace):
    with pytest.raises(ValueError, match='disposable navigation fixture'):
        with fixture_module().terminal_tab_fixture('http://127.0.0.1:1', 'unused', workspace):
            pytest.fail('Nonfixture scope was accepted')


@pytest.mark.parametrize('fail_second', [False, True])
def test_terminal_fixture_cleans_only_created_sessions(monkeypatch, tmp_path, fail_second):
    from core.routes import term
    module = fixture_module()
    monkeypatch.syspath_prepend(str(ROOT / 'scripts/perf'))
    workspace = tmp_path / 'lab-navigation-test/vault/workspaces/alpha'
    requests, commands = [], []

    def request(req, timeout):
        requests.append(req)
        if req.method == 'POST':
            count = sum(r.method == 'POST' for r in requests)
            return io.BytesIO(json.dumps({'name': f'owned-{count}'}).encode())
        return io.BytesIO(b'{"ok":true}')

    def run(command, **kwargs):
        commands.append(command)
        if fail_second and len(commands) == 2:
            raise RuntimeError('Spawn failed')

    monkeypatch.setattr(module.urllib.request, 'urlopen', request)
    monkeypatch.setattr(module.subprocess, 'run', run)
    monkeypatch.setattr(term, '_tmux_find_session_socket', lambda name: 'owned-socket')
    monkeypatch.setattr(term, '_tmux_command', lambda socket, *args: ['tmux', '-L', socket, *args])
    if fail_second:
        with pytest.raises(RuntimeError, match='Spawn failed'):
            with module.terminal_tab_fixture('http://127.0.0.1:1', 'unused', workspace, count=3):
                pytest.fail('Partial setup was yielded')
    else:
        with module.terminal_tab_fixture('http://127.0.0.1:1', 'unused', workspace, count=3) as rows:
            assert [r['name'] for r in rows] == ['owned-1', 'owned-2', 'owned-3']
            assert len({r['marker'] for r in rows}) == 3
    count = 2 if fail_second else 3
    assert [r.full_url for r in requests if r.method == 'DELETE'] == [
        f'http://127.0.0.1:1/api/term/sessions/owned-{i}?purge=true' for i in range(1, count + 1)]
    assert [command[:7] for command in commands] == [
        ['tmux', '-L', 'owned-socket', 'respawn-pane', '-k', '-t', f'owned-{i}'] for i in range(1, count + 1)]
    assert all(json.loads(r.data)['cwd'] == str(workspace) for r in requests if r.method == 'POST')
