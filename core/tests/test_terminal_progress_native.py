import json
import time

from click.testing import CliRunner

from core import terminal_progress as supervisor
from core.routes import term
from lab import terminal_context, terminal_progress as progress, terminal_status
from lab.cli import main
from .test_term_creation_native import native_creation_tmux, native_creation_client  # noqa: F401


def test_real_hook_supervisor_api_and_stale_write_protection(
        native_creation_tmux, native_creation_client, seed_workspace, monorepo, monkeypatch):
    run, socket, _ = native_creation_tmux
    seed_workspace('demo')
    monkeypatch.setattr(term.lab_paths, 'find_framework_root', lambda: monorepo)
    monkeypatch.setattr(supervisor.terminal_cleanup, '_roots', lambda root: [{'id': 'fixture', 'path': root}])
    client = native_creation_client
    created = client.post('/api/term/sessions', json={'workspace_id': 'demo', 'kind': 'terminal'})
    assert created.status_code == 200, created.text
    name = created.json()['name']
    pane = run('display-message', '-p', '-t', name, '#{pane_id}').stdout.strip()
    socket_path = run('display-message', '-p', '#{socket_path}').stdout.strip()
    pid = run('display-message', '-p', '#{pid}').stdout.strip()
    monkeypatch.setenv('TMUX', f'{socket_path},{pid},0')
    monkeypatch.setenv('TMUX_PANE', pane)
    terminal = terminal_context.current()
    terminal.set_option(terminal_status.LLM_OPTION, 'copilot')
    now = time.time()
    progress.handle_hook('prompt', {'sessionId': 'native-copilot'}, terminal, now=now-1900)
    report = {'version': 1, 'state': 'working', 'id': 'a'*32, 'message': 'Checking native progress',
              'updated_at': now-1801, 'revision': time.monotonic_ns()//1000}
    terminal.set_option(terminal_status.OPTION, terminal_status.encode(report))
    result = CliRunner().invoke(main, ['progress', 'hook', 'post-tool'], input='{"sessionId":"native-copilot"}')
    assert result.exit_code == 0 and '20 minutes' in json.loads(result.stdout)['additionalContext']
    monitor = supervisor.Supervisor(now=now-120)
    assert monitor.tick(monorepo, now=now)['new_alerts'] == 1
    listing = client.get('/api/term/sessions', params={'workspace_id': 'demo'}).json()
    current, = [row for row in listing if row['name'] == name]
    alert = current['terminal_progress']['alert']
    assert alert['active'] and alert['kind'] == 'stale'
    assert current['terminal_status'] == report, 'supervisor never writes an agent report'
    assert current['terminal_progress']['last_activity_at'] > report['updated_at']
    batch = client.get('/api/workspace-documents/attention').json()
    notice = next(row for rows in batch.values() for row in rows if row['name'] == name)
    assert notice['terminal_progress']['alert'] == alert and notice['workspace_id'] == 'demo'
    assert not any(key.startswith('_progress_') for key in current), 'CAS tokens stay internal'
    assert supervisor.Supervisor(now=now-120).tick(monorepo, now=now)['new_alerts'] == 0
    old = next(row for row in term._tmux_list('lab-owned-', progress=True) if row['name'] == name)
    result = CliRunner().invoke(main, ['notifications', 'working', 'Native progress checks passed'])
    assert result.exit_code == 0, result.output
    assert not supervisor.persist(old, alert), 'a report that races the scan wins atomically'
    current = client.get('/api/term/sessions', params={'workspace_id': 'demo'}).json()[0]
    assert not current['terminal_progress']['alert']['active']
    assert current['terminal_progress']['alert']['id'] == alert['id'], 'resolved history is retained'
    run('kill-session', '-t', name)
    run('new-session', '-d', '-s', name, '/bin/sleep 60')
    assert not supervisor.persist(old, alert), 'a recreated session never receives the old alert'
    assert run('show-options', '-qv', '-t', name, progress.ALERT_OPTION).stdout.strip() == ''
