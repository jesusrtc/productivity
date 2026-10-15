"""Real CLI → owned tmux option → Lab API, on a private disposable socket."""
import json
import os
import shutil
import sys
import time

from click.testing import CliRunner
import pytest

from lab.cli import main
from lab import agent_context
from core import terminal_llm
from core.routes import term
from .test_term_creation_native import native_creation_tmux, native_creation_client  # noqa: F401


def test_native_agent_reports_follow_exact_pane_and_survive_backend_reads(
        native_creation_tmux, native_creation_client, seed_workspace, monorepo, monkeypatch):
    run, socket, _ = native_creation_tmux
    seed_workspace('demo')
    monkeypatch.setattr(term.lab_paths, 'find_framework_root', lambda:monorepo)
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
    assert client.get('/api/term/sessions',params={'workspace_id':'demo'}).json()[0]['llm_controlled'] is None
    for enabled in (True, True, False, True):
        result = CliRunner().invoke(main, ['terminal','llm', *([] if enabled else ['--off'])])
        assert result.exit_code == 0, result.output
        row = client.get('/api/term/sessions',params={'workspace_id':'demo'}).json()[0]
        assert row['llm_controlled'] is enabled
        assert row['terminal_status'] is None, 'marking LLM control is not a work report'
        assert run('show-options','-qv','-t','lab-owned-unrelated','@lab_llm').stdout == ''
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
        messages = client.get('/api/workspace-documents/attention').json()
        reported = next(item for rows in messages.values() for item in rows if item['name'] == name)
        assert reported['workspace_id'] == 'demo' and reported['logical_name']
        assert reported['terminal_status'] == row['terminal_status']
        assert reported['tmux_id'] == row['tmux_id']
        again = client.get('/api/term/sessions',params={'workspace_id':'demo'}).json()[0]
        assert again['terminal_status'] == row['terminal_status'], 'ordinary reads do not change a report'
        assert run('show-options','-qv','-t','lab-owned-unrelated','@lab_status').stdout == ''
    old_id = row['tmux_id']
    run('kill-session','-t',name)
    run('new-session','-d','-s',name,'/bin/sleep 60')
    replacement = client.get('/api/term/sessions',params={'workspace_id':'demo'}).json()[0]
    assert replacement['tmux_id'] != old_id
    assert replacement['terminal_status'] is None, 'a new session cannot inherit the old report'
    assert replacement['llm_controlled'] is None, 'LLM control belongs to the session incarnation'


def test_native_launch_bootstraps_full_context_and_updates_only_its_session(
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
    assert 'run `lab context llm` before other tools' in guide
    assert '# Lab user guide' not in guide
    assert received['version'] == version
    assert run('show-options','-qv','-t','lab-owned-context','@lab_llm').stdout.strip() == 'codex'
    assert run('show-options','-qv','-t','lab-owned-context',agent_context.CONTEXT_VERSION_OPTION).stdout.strip() == ''
    pane = run('display-message','-p','-t','lab-owned-context','#{pane_id}').stdout.strip()
    socket_path = run('display-message','-p','#{socket_path}').stdout.strip()
    server_pid = run('display-message','-p','#{pid}').stdout.strip()
    monkeypatch.setenv('TMUX',f'{socket_path},{server_pid},0')
    monkeypatch.setenv('TMUX_PANE',pane)
    for _ in range(2):
        result = CliRunner().invoke(main, ['context','llm'])
        assert result.exit_code == 0 and '# Lab user guide' in result.output
        assert agent_context.read_context('changelog').strip() not in result.output
        assert CliRunner().invoke(main, ['context','update']).output == ''
    assert run('show-options','-qv','-t','lab-owned-context',agent_context.CONTEXT_VERSION_OPTION).stdout.strip() == version
    assert run('show-options','-qv','-t','lab-owned-context','@lab_llm').stdout.strip() == 'codex'
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


def test_native_manual_agent_is_marked_and_identity_survives_later_listings(
        native_creation_tmux, native_creation_client, seed_workspace, tmp_path, monkeypatch):
    run, socket, _ = native_creation_tmux
    seed_workspace('demo')
    # An owned inert script exercises real OS process discovery, without
    # prompting or spending tokens in a user's actual provider.
    node = shutil.which('node')
    if not node:
        pytest.skip('Node required for the owned provider fixture')
    provider = tmp_path / 'node_modules/@openai/codex/bin/codex.js'
    provider.parent.mkdir(parents=True)
    provider.write_text('setTimeout(() => {}, 60000);')
    monkeypatch.setattr(term, '_enrich_session_details', terminal_llm.enrich)
    client = native_creation_client
    name = client.post('/api/term/sessions',json={'workspace_id':'demo','kind':'terminal'}).json()['name']
    assert not client.get('/api/term/sessions',params={'workspace_id':'demo'}).json()[0]['llm_controlled']
    run('respawn-pane','-k','-t',name,node,str(provider))
    deadline = time.monotonic()+5
    while True:
        row = client.get('/api/term/sessions',params={'workspace_id':'demo'}).json()[0]
        if row['llm_controlled']:
            break
        assert time.monotonic()<deadline, row
        time.sleep(.02)
    assert row['agent']=='codex' and row['terminal_status'] is None
    assert run('show-options','-qv','-t',name,'@lab_llm').stdout.strip()=='codex'
    row = client.get('/api/term/sessions',params={'workspace_id':'demo'}).json()[0]
    assert row['agent']=='codex' and row['llm_controlled'], 'persisted marker preserves detected identity'
    run('set-option','-t',name,'@lab_llm','0')
    assert not client.get('/api/term/sessions',params={'workspace_id':'demo'}).json()[0]['llm_controlled']
