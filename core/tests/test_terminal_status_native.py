"""Real CLI → owned tmux option → Lab API, on a private disposable socket."""
import json
import os
import sys
import time

from click.testing import CliRunner
import pytest

from lab.cli import main
from lab import agent_context
from core.routes import term
from .test_term_creation_native import native_creation_tmux, native_creation_client  # noqa: F401


def test_native_agent_reports_follow_exact_pane_and_survive_backend_reads(
        native_creation_tmux, native_creation_client, seed_workspace, monkeypatch):
    run, socket, _ = native_creation_tmux
    seed_workspace('demo')
    client = native_creation_client
    response = client.post('/api/term/sessions', json={'workspace_id':'demo','kind':'terminal'})
    assert response.status_code == 200, response.text
    name = response.json()['name']
    pane = run('display-message','-p','-t',name,'#{pane_id}').stdout.strip()
    socket_path = run('display-message','-p','#{socket_path}').stdout.strip()
    server_pid = run('display-message','-p','#{pid}').stdout.strip()
    monkeypatch.setenv('TMUX',f'{socket_path},{server_pid},0')
    monkeypatch.setenv('TMUX_PANE',pane)
    # Another session is active in the server, and routing for NEW terminals
    # points somewhere else. Reporting still belongs to this exact pane/socket.
    run('new-session','-d','-s','lab-owned-unrelated','/bin/sleep 60')
    monkeypatch.setattr(term, '_enrich_session_details', lambda rows:None)
    message = 'Review | <preview> ; #{session_name}\n¿Listo?'
    for state in ('working','attention','finished'):
        result = CliRunner().invoke(main,['notifications',state,message])
        assert result.exit_code == 0, result.output
        listing = client.get('/api/term/sessions',params={'workspace_id':'demo'})
        assert listing.status_code == 200, listing.text
        row, = listing.json()
        assert row['terminal_status']['state'] == state
        assert row['terminal_status']['message'] == message
        assert row['tmux_socket'] == socket and row['tmux_id'].startswith('$')
        assert 'output_activity' not in row
        again = client.get('/api/term/sessions',params={'workspace_id':'demo'}).json()[0]
        assert again['terminal_status'] == row['terminal_status'], 'ordinary reads do not change a report'
        assert run('show-options','-qv','-t','lab-owned-unrelated','@lab_status').stdout == ''
    old_id = row['tmux_id']
    run('kill-session','-t',name)
    run('new-session','-d','-s',name,'/bin/sleep 60')
    replacement = client.get('/api/term/sessions',params={'workspace_id':'demo'}).json()[0]
    assert replacement['tmux_id'] != old_id
    assert replacement['terminal_status'] is None, 'a new session cannot inherit the old report'


def test_native_launch_records_context_and_updates_only_its_session(
        native_creation_tmux, monorepo, tmp_path, monkeypatch):
    run, _, _ = native_creation_tmux
    captured = tmp_path / 'received.json'
    provider = tmp_path / 'codex'
    provider.write_text(f'#!{sys.executable}\n'
        'import json,os,sys,time\n'
        'if "app-server" in sys.argv:\n'
        ' for line in sys.stdin:\n'
        '  r=json.loads(line)\n'
        '  result={"config":{}} if r["method"]=="config/read" else {}\n'
        '  print(json.dumps({"id":r["id"],"result":result}),flush=True)\n'
        'else:\n'
        f' with open({str(captured)!r},"w") as f:\n'
        '  json.dump({"argv":sys.argv,"version":os.environ.get("LAB_AGENT_CONTEXT_VERSION")},f)\n'
        ' time.sleep(60)\n')
    provider.chmod(0o700)
    command = ['env', 'PATH='+str(tmp_path)+os.pathsep+os.environ['PATH'],
               sys.executable, '-m', 'lab', 'agents', 'run', '--vault', str(monorepo), 'codex']
    # Multi-argument tmux exec bypasses the fixture's inert default shell.
    run('new-session', '-d', '-s', 'lab-owned-context', '-c', str(monorepo), *command)
    deadline = time.monotonic() + 10
    while not captured.exists() or not captured.stat().st_size:
        assert time.monotonic() < deadline, run('capture-pane','-p','-t','lab-owned-context').stdout
        time.sleep(.02)
    received = json.loads(captured.read_text())
    guide = json.loads(received['argv'][2].split('=',1)[1])
    version = agent_context.context_version()
    assert f'Lab context version: {version}.' in guide
    assert 'You are in Lab terminal `lab-owned-context`' in guide
    assert received['version'] == version
    assert run('show-options','-qv','-t','lab-owned-context',agent_context.CONTEXT_VERSION_OPTION).stdout.strip() == version
    pane = run('display-message','-p','-t','lab-owned-context','#{pane_id}').stdout.strip()
    socket_path = run('display-message','-p','#{socket_path}').stdout.strip()
    server_pid = run('display-message','-p','#{pid}').stdout.strip()
    monkeypatch.setenv('TMUX',f'{socket_path},{server_pid},0')
    monkeypatch.setenv('TMUX_PANE',pane)
    result = CliRunner().invoke(main, ['context','update'])
    assert result.exit_code == 0 and result.output == ''
    # Simulate a running agent having an older guide. Another pane/session and
    # ordinary context reads cannot consume its pending refresh.
    run('set-option','-t','lab-owned-context',agent_context.CONTEXT_VERSION_OPTION,'old')
    run('new-session','-d','-s','lab-owned-other','/bin/sleep 60')
    assert CliRunner().invoke(main, ['context']).exit_code == 0
    assert run('show-options','-qv','-t','lab-owned-context',agent_context.CONTEXT_VERSION_OPTION).stdout.strip() == 'old'
    result = CliRunner().invoke(main, ['context','update'])
    assert result.exit_code == 0 and f'Lab context version: {version}.' in result.output
    assert CliRunner().invoke(main, ['context','update']).output == ''
    assert run('show-options','-qv','-t','lab-owned-other',agent_context.CONTEXT_VERSION_OPTION).stdout == ''
