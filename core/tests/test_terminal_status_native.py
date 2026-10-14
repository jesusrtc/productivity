"""Real CLI → owned tmux option → Lab API, on a private disposable socket."""
from click.testing import CliRunner
import pytest

from lab.cli import main
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
