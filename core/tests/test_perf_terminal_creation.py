"""Native creation requires owned processes, real rendered echo and saved identity."""
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys

import pytest

from .test_frontend_terminal_ui import ROOT, _run_node


def fixture_module():
    spec = importlib.util.spec_from_file_location('creation_fixture', ROOT / 'scripts/perf/terminal_creation_fixture.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('workspace', ['/', '/tmp/user/vault/workspaces/alpha', '/tmp/lab-navigation-test/vault/workspaces/beta'])
def test_creation_rejects_foreign_workspace(workspace):
    with pytest.raises(ValueError, match='disposable'):
        with fixture_module().terminal_creation_fixture('http://127.0.0.1:1', 'unused', workspace):
            pytest.fail('Foreign workspace accepted')


@pytest.mark.parametrize('fail_workload,foreign', [(False, False), (True, False), (False, True)])
def test_creation_cleanup_preserves_foreign_sessions_and_restores_shell(monkeypatch, tmp_path, fail_workload, foreign):
    from core.routes import term
    module = fixture_module()
    monkeypatch.syspath_prepend(str(ROOT / 'scripts/perf'))
    monkeypatch.setenv('SHELL', '/owned/previous-shell')
    workspace = tmp_path / 'lab-navigation-test/vault/workspaces/alpha'
    workspace.mkdir(parents=True)
    live, requests, deleted = {}, [], []

    def request(req, timeout):
        requests.append(req)
        if req.method == 'DELETE':
            name = req.full_url.split('/api/term/sessions/')[1].split('?')[0]
            deleted.append(name)
            live.pop(name)
            body = {'ok': True}
        elif req.full_url.endswith('/saved?workspace_id=alpha'):
            body = [{'name': row['logical_name']} for row in live.values()]
        elif req.method == 'POST':
            assert json.loads(req.data) == {'workspace_id': 'alpha', 'enabled': False}
            body = {'enabled': False}
        else:
            body = list(live.values())
        return io.BytesIO(json.dumps(body).encode())

    monkeypatch.setattr(module.urllib.request, 'urlopen', request)
    monkeypatch.setattr(term, '_tmux_find_session_socket', lambda name: 'owned' if any(key.startswith(name) for key in live) else None)
    monkeypatch.setattr(term, '_tmux_session_info', lambda name: live.get(name))
    monkeypatch.setattr(term, '_tmux_command', lambda socket, *args: ['tmux', '-L', socket, *args])
    monkeypatch.setattr(module.subprocess, 'check_output', lambda argv, **kwargs: str(live[argv[-2]]['pid']))

    def run():
        with module.terminal_creation_fixture('http://127.0.0.1:1', 'unused', workspace) as report:
            assert module.os.environ['SHELL'] == report['shell']
            assert Path(report['shell']).stat().st_mode & 0o700 == 0o700
            for index in (2, 20):
                name = f'lab-navigation-test-alpha-bash-{index}'
                pid = 2**30 + index
                live[name] = {'name': name, 'logical_name': f'bash-{index}', 'kind': 'terminal',
                              'cwd': str(workspace), 'cmd': report['shell'] + ' -l', 'pid': pid}
                process_record = workspace.parents[2] / 'terminal-create-processes' / f'{pid}.json'
                process_record.write_text(json.dumps({'pid': pid, 'cwd': str(workspace)}))
                epoch_ns = 1_700_000_000_000_000_000 + index * 1_000_000
                module.os.utime(process_record, ns=(epoch_ns, epoch_ns))
            if foreign:
                live['user-session'] = {'name': 'user-session', 'logical_name': 'user',
                                        'kind': 'terminal', 'cwd': str(workspace), 'cmd': '/user/shell'}
            if fail_workload:
                raise RuntimeError('Owned workload failed')
        assert report['cleaned'] and len(report['processes']) == 2 and len(report['sessions']) == 2
        assert [row['processRecordEpoch'] for row in report['processes']] == [
            1_700_000_000_002, 1_700_000_000_020]
        assert [row['name'] for row in report['processes']] == deleted

    if foreign or fail_workload:
        with pytest.raises(RuntimeError, match='Unexpected session preserved' if foreign else 'Owned workload failed'):
            run()
    else:
        run()
    assert deleted == ['lab-navigation-test-alpha-bash-2', 'lab-navigation-test-alpha-bash-20']
    assert list(live) == (['user-session'] if foreign else [])
    assert module.os.environ['SHELL'] == '/owned/previous-shell'


def test_creation_observer_requires_exact_count_scope_kind_and_render_readiness():
    source = (ROOT / 'scripts/perf/terminal_creation_workload.mjs').read_text()
    install = source[source.index('function installCreation('):source.index('export async function verifyTerminalCreation')]
    result = _run_node(r'''
const window={};let currentWorkspace={path:'/fixture/alpha'},termSessions=[];
const seen=[],calls=[],known=new Map();let ready=true,open=false,rowCount=0;
const __terminalTabs={addFixture:(name,marker)=>known.set(name,marker),ready:name=>ready&&known.has(name),snapshot:()=>({})};
const document={querySelectorAll:()=>Array(rowCount),getElementById:()=>({classList:{contains:()=>open}})};
let termAttach=(name)=>{calls.push(name);if(!known.has(name))throw Error('Observer registered too late');};
''' + install + r'''
installCreation('created-marker','/fixture/alpha','owned-');const probe=window.__terminalCreation;
termAttach('owned-one');termSessions=[{name:'owned-one',logical_name:'bash',kind:'terminal',workspace_id:'alpha'}];rowCount=1;
seen.push(probe.ready(1));ready=false;seen.push(!probe.ready(1));ready=true;
open=true;seen.push(!probe.ready(1));open=false;
rowCount=2;seen.push(!probe.ready(1));rowCount=1;
termSessions[0].kind='claude';seen.push(!probe.ready(1));termSessions[0].kind='terminal';
termSessions[0].workspace_id='beta';seen.push(!probe.ready(1));termSessions[0].workspace_id='alpha';
termAttach('owned-one');seen.push(probe.snapshot().names.length===1);
for(const foreign of ['user-session','owned-two']) {
 if(foreign==='owned-two')currentWorkspace.path='/fixture/beta';
 try{termAttach(foreign);seen.push(false);}catch{seen.push(true);}
}
console.log(JSON.stringify({seen,calls,names:probe.snapshot().names}));
''')
    assert len(result['seen']) == 9 and all(result['seen'])
    assert result['calls'] == ['owned-one', 'owned-one']
    assert result['names'] == ['owned-one']


@pytest.mark.parametrize('options', [
    ['--typing'], ['--resize'], ['--create'], ['--settings'], ['--pins'],
    ['--terminal-tabs'], ['--quick-files'], ['--document-edit'], ['--notebook-view'],
    ['--navigation-refresh-delay', '1'],
])
def test_creation_cli_rejects_mixed_workflows_before_creating_resources(options):
    result = subprocess.run([sys.executable, str(ROOT / 'scripts/perf/lab_navigation_latency.py'),
                             '--terminal-create', *options], capture_output=True, text=True)
    assert result.returncode == 2
    assert 'workflow' in result.stderr and not result.stdout


@pytest.mark.parametrize('base_url', ['https://example.com', 'http://127.0.0.2:1'])
def test_creation_rejects_nonlocal_server_before_network(monkeypatch, base_url):
    module = fixture_module()
    monkeypatch.setattr(module.urllib.request, 'urlopen', lambda *a, **k: pytest.fail('Network used'))
    with pytest.raises(ValueError, match='disposable'):
        with module.terminal_creation_fixture(base_url, 'unused', '/tmp/lab-navigation-test/vault/workspaces/alpha'):
            pytest.fail('Nonlocal server accepted')
