"""Owned echo CLI for document-terminal launch/attach in navigation fixtures."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import uuid


@contextmanager
def assistant_terminal_fixture(root, *, trace_launch=False):
    root = Path(root).resolve()
    base = root.parent
    if root.name != 'assistant' or not base.name.startswith('lab-navigation-'):
        raise ValueError('Document terminals require the disposable navigation fixture')
    if Path(os.environ.get('LAB_HOME', '')).resolve() != base/'config':
        raise ValueError('Document terminal configuration must be fixture-owned')
    from core.routes import term
    from lab import settings, tmux_sockets
    from lab_terminal_latency import echo_program
    tmux = shutil.which('tmux')
    if not tmux:
        raise RuntimeError('tmux is required')
    previous_env = {key:os.environ.get(key) for key in ('PATH', 'TMUX_TMPDIR')}
    previous_state = tmux_sockets.read_state()
    binary_dir = base/'detail-bin'
    binary_dir.mkdir()
    processes = base/'detail-processes'
    processes.mkdir()
    marker = 'detail-'+uuid.uuid4().hex[:12]
    binary = binary_dir/'claude'
    launch_header = ('import time\nprovider_enter=time.time_ns()/1_000_000\n'
                     'provider_cpu=time.process_time_ns()/1_000_000\n') if trace_launch else ''
    launch_fields = (',"providerEntryEpoch":provider_enter,"providerEntryCpuMs":provider_cpu,'
                     '"handoffEpoch":float(os.environ["LAB_PERF_DOCUMENT_EXEC_EPOCH"]) '
                     'if "LAB_PERF_DOCUMENT_EXEC_EPOCH" in os.environ else None') if trace_launch else ''
    binary.write_text(f'#!{sys.executable}\n'+launch_header+'import json,os,sys\nfrom pathlib import Path\n'
        'if "--version" in sys.argv:\n print("2.1.0");sys.exit(0)\n'
        f'Path({str(processes)!r},str(os.getpid())+".json").write_text('
        'json.dumps({"pid":os.getpid(),"cwd":os.getcwd(),"context":os.environ.get("LAB_DOCUMENT_CONTEXT")'+launch_fields+'}))\n'+echo_program(marker)+'\n')
    binary.chmod(0o700)
    settings.update_global(root, {'defaultAgent':'claude', 'autopilot':{'claude':False}})
    report = dict(marker=marker, agent='owned-echo-cli', socketMode='private', processes=[], cleaned=False)
    from agent_launch_probe import document_launch_trace
    with document_launch_trace(root, enabled=trace_launch) as launch_trace, tempfile.TemporaryDirectory(prefix='lab-detail-tmux-', dir='/tmp') as directory:
        report['launchTrace'] = launch_trace
        os.environ.update(PATH=str(binary_dir)+':'+os.environ['PATH'], TMUX_TMPDIR=directory)
        env = term._tmux_child_env()
        socket_name = 'detail-echo'
        def run(*args, check=True):
            return subprocess.run([tmux, '-L', socket_name, *args], capture_output=True,
                text=True, env=env, check=check, timeout=10)
        server_pid = None
        try:
            run('-f', '/dev/null', 'new-session', '-d', '-s', 'anchor', '/bin/sleep 3600')
            server_pid = int(run('display-message', '-p', '#{pid}').stdout)
            run('set-option', '-g', 'default-shell', '/bin/sh')
            tmux_sockets.write_state({'version':1, 'active':socket_name,
                'generations':[{'name':socket_name, 'status':'active', 'created_at':time.time()}]})
            term._invalidate_workspace_term_caches()
            yield report
        finally:
            try:
                registry = root/'.lab/state/document-terminals.json'
                entries = json.loads(registry.read_text())['terminals'] if registry.exists() else {}
                report['terminals'] = [{key:entry.get(key) for key in ('name','pane_pid','socket','state','document_id','cwd')}
                                       for entry in entries.values()]
                # Read the existing launch marker's timestamp only at cleanup;
                # do not add filesystem operations to the measured startup.
                report['processes'] = [{**json.loads(path.read_text()),
                    'processRecordEpoch':path.stat().st_mtime_ns/1_000_000}
                    for path in processes.glob('*.json')]
                panes = run('list-panes', '-a', '-F', '#{pane_pid}|#{session_name}|#{pane_current_path}')
                report['panes'] = [dict(pid=int(pid), name=name, cwd=cwd)
                                   for pid,name,cwd in (line.split('|',2) for line in panes.stdout.splitlines())]
                assert all(entry['name'].startswith(base.name+'-') and entry['cwd']==str(root)
                           and entry['socket']==socket_name for entry in entries.values())
                for item in report['processes']:
                    assert item['cwd'] == str(root)
                    assert any(pane['pid']==item['pid'] and pane['name'].startswith(base.name+'-')
                               and pane['cwd']==str(root) for pane in report['panes'])
                for entry in entries.values():
                    assert any(item['pid']==entry['pane_pid']
                               and item['context']==str(root/'.lab/state/document-context'/(entry['key']+'.json'))
                               for item in report['processes'])
            finally:
                try:
                    # All processes on this private socket belong to this fixture.
                    panes = run('list-panes', '-a', '-F', '#{pane_pid}', check=False)
                    pids = {int(pid) for pid in panes.stdout.splitlines()}
                    if server_pid is not None:
                        pids.add(server_pid)
                    run('kill-server', check=False)
                    assert run('list-sessions', check=False).returncode != 0
                    deadline = time.monotonic()+5
                    while pids:
                        for pid in list(pids):
                            try:
                                os.kill(pid, 0)
                            except ProcessLookupError:
                                pids.remove(pid)
                        if pids and time.monotonic() > deadline:
                            raise RuntimeError('Owned document-terminal processes did not exit')
                        if pids:
                            time.sleep(.01)
                    report['cleaned'] = True
                finally:
                    try:
                        tmux_sockets.write_state(previous_state)
                    finally:
                        for key, value in previous_env.items():
                            if value is None:
                                os.environ.pop(key, None)
                            else:
                                os.environ[key] = value
                        term._invalidate_workspace_term_caches()
