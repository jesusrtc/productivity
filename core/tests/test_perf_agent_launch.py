"""The optional launcher probe keeps the ordinary CLI/provider boundary."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.fixture
def probe(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2]/'scripts/perf'))
    import agent_launch_probe
    return agent_launch_probe


def test_traced_launcher_keeps_argv_environment_pid_and_site_hooks(probe, tmp_path):
    root = tmp_path/'assistant'
    binary_dir = tmp_path/'binary with spaces'
    trace_dir = tmp_path/'trace'
    for folder in (root, binary_dir, trace_dir):
        folder.mkdir()
    provider = binary_dir/'claude'
    provider.write_text(f'#!{sys.executable}\n'
        'import json,os,sys,time\n'
        'print(json.dumps(dict(pid=os.getpid(),epoch=time.time_ns()/1_000_000,args=sys.argv[1:],'
        'vault=os.environ.get("LAB_VAULT"),context=os.environ.get("LAB_DOCUMENT_CONTEXT"),'
        'siteLoaded="site" in sys.modules,customize=getattr(sys.modules.get("sitecustomize"),"__file__",None),'
        'handoff=os.environ.get("LAB_PERF_DOCUMENT_EXEC_EPOCH"))))\n')
    provider.chmod(0o700)
    context = str(root/'document context.json')
    env = {**os.environ, 'PATH':str(binary_dir)+os.pathsep+os.environ['PATH'],
           'LAB_DOCUMENT_CONTEXT':context, 'LAB_HOME':str(tmp_path/'config')}
    argv = [sys.executable, '-m', 'lab', 'agents', 'run', '--vault', str(root),
            'claude', '--', '--session-id', 'saved-id', '--model', 'model with spaces']
    original = subprocess.run(argv, cwd=root, env=env, capture_output=True, text=True)
    observed = subprocess.run(probe.traced_argv(argv, trace_dir, provider),
                              cwd=root, env=env, capture_output=True, text=True)
    assert original.returncode == observed.returncode == 0, (original.stderr, observed.stderr)
    before, after = json.loads(original.stdout), json.loads(observed.stdout)
    assert {k:v for k,v in before.items() if k not in {'pid','epoch','handoff'}} == {
        k:v for k,v in after.items() if k not in {'pid','epoch','handoff'}}
    assert after['siteLoaded'] and after['vault'] == str(root.resolve()) and after['context'] == context
    traces = list(trace_dir.glob('*.json'))
    assert len(traces) == 1
    trace = json.loads(traces[0].read_text())
    assert trace['pid'] == after['pid']
    ready, execute = trace['events']
    assert ready['phase'] == 'interpreter-ready' and execute['phase'] == 'provider-exec'
    assert ready['epoch'] <= execute['epoch'] <= float(after['handoff']) <= after['epoch']
    assert ready['cpuMs'] <= execute['cpuMs']
    assert all(set(event) == {'phase','epoch','cpuMs'} for event in trace['events'])
    assert not (root/'sitecustomize.py').exists()
    refused = subprocess.run(probe.traced_argv(argv, trace_dir, binary_dir/'unowned'),
                             cwd=root, env=env, capture_output=True, text=True)
    assert refused.returncode != 0 and 'Unowned agent' in refused.stderr and not refused.stdout


def test_launch_probe_rejects_other_commands_and_restores_on_error(probe, tmp_path, monkeypatch):
    from core import document_terminals
    original = document_terminals._argv
    with pytest.raises(ValueError, match='Unexpected document launcher'):
        probe.traced_argv([sys.executable, '-m', 'something-else'], tmp_path, tmp_path/'claude')
    with probe.document_launch_trace(tmp_path, enabled=False) as disabled:
        assert disabled is None
        assert document_terminals._argv is original
    with pytest.raises(ValueError, match='disposable fixture'):
        with probe.document_launch_trace(tmp_path/'assistant', enabled=True):
            pytest.fail('Accepted unowned fixture')
    root = tmp_path/'lab-navigation-owned'/'assistant'
    root.mkdir(parents=True)
    monkeypatch.setenv('LAB_HOME', str(tmp_path/'user-config'))
    with pytest.raises(ValueError, match='fixture-owned configuration'):
        with probe.document_launch_trace(root, enabled=True):
            pytest.fail('Accepted unowned configuration')
    monkeypatch.setenv('LAB_HOME', str(root.parent/'config'))
    with pytest.raises(RuntimeError, match='fixture failed'):
        with probe.document_launch_trace(root, enabled=True) as report:
            assert document_terminals._argv is not original
            with pytest.raises(ValueError, match='crossed fixture scope'):
                document_terminals._argv(tmp_path, {})
            raise RuntimeError('fixture failed')
    assert document_terminals._argv is original and report['restored']
