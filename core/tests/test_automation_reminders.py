import copy
from core import automation_reminders as reminders, terminal_automation_lifecycle as lifecycle, terminal_progress as supervisor
from core.routes import term
from lab import terminal_status
from .test_term_creation_native import native_creation_tmux, native_creation_client  # noqa: F401
from .test_terminal_automations import _save, _launch
from .test_terminal_automation_lifecycle import _status


def group():
    main = {'name': 'main', 'tmux_socket': 'owned', 'tmux_id': '$1', 'created': 100,
            'pane_id': '%1', 'pane_pid': 10, 'pane_tty': '/dev/ttys001'}
    child = {**main, 'name': 'child', 'tmux_id': '$2', 'pane_id': '%2', 'pane_pid': 20}
    run = {'command': 'ssh host', 'shell': '/bin/sh', 'launch_id': 'launch', 'updated_at': 100,
           'health_command': 'never execute a new connection'}
    return {'main': main, 'members': [('child', run, child)]}


def test_recurring_checkins_keep_unknown_stopped_and_new_launches_distinct():
    current = group()
    snapshot = {20: {'ppid': 1, 'stat': 'S', 'comm': 'sh'},
                21: {'ppid': 20, 'stat': 'S', 'comm': 'ssh'}}
    assert reminders.next_alert(current, snapshot, None, 1899) is None
    first = reminders.next_alert(current, snapshot, None, 1900)
    assert first['kind'] == 'automation' and first['active']
    assert reminders.next_alert(current, snapshot, first, 1901) is None
    second = reminders.next_alert(current, snapshot, first, 3700)
    assert second['id'] != first['id'] and second['source'] == first['source']
    assert reminders.next_alert(current, None, second, 3800) is None, 'unknown is never stopped'
    assert reminders.next_alert(current, {20: snapshot[20]}, second, 3800) == {**second, 'active': False}
    renewed = copy.deepcopy(current)
    renewed['members'][0][1].update(launch_id='renewed', updated_at=3800)
    resolved = reminders.next_alert(renewed, snapshot, second, 3801)
    assert not resolved['active'], 'renewal starts a fresh 30-minute window'
    assert reminders.next_alert(renewed, snapshot, resolved, 5599) is None
    assert reminders.next_alert(renewed, snapshot, resolved, 5600)['source'] != first['source']
    current['main']['pane_dead'] = True
    assert not reminders.next_alert(current, snapshot, second, 4000)['active']


def test_group_main_follows_saved_hierarchy_and_rejects_cycles():
    saved = {'parent': {'parent_terminal': None}, 'first': {'parent_terminal': 'parent'},
             'child': {'parent_terminal': 'first'}}
    assert reminders._main(saved, 'child') == 'parent'
    saved['first']['automation_appearance'] = {'role': 'main'}
    assert reminders._main(saved, 'child') == 'first', 'nested automation uses its own main'
    del saved['first']['automation_appearance']
    saved['parent']['parent_terminal'] = 'child'
    assert reminders._main(saved, 'child') is None
    assert reminders._main({'orphan': {'automation_appearance': {'role': 'child'}}}, 'orphan') is None
    assert reminders.decode(terminal_status.encode({'version': 1, 'active': True})) is None


def test_remote_scripts_are_detected_without_alerting_for_local_automations():
    current = group()
    current['members'][0][1]['command'] = 'make connect'
    snapshot = {20: {'ppid': 1, 'stat': 'S', 'comm': 'sh'},
                21: {'ppid': 20, 'stat': 'S', 'comm': 'ssh'}}
    assert reminders.next_alert(current, snapshot, None, 1900)
    snapshot[21]['comm'] = 'tmux: client'
    assert reminders.next_alert(current, snapshot, None, 1900)
    snapshot[21]['comm'] = 'sleep'
    assert reminders.next_alert(current, snapshot, None, 1900) is None


def test_native_ssh_group_notifies_only_main_repeats_and_resolves(
        native_creation_tmux, native_creation_client, seed_workspace, monorepo, monkeypatch):
    run, _, _ = native_creation_tmux
    client = native_creation_client
    folder = seed_workspace('demo')
    monkeypatch.setenv('SHELL', '/bin/sh')
    monkeypatch.setattr(term.lab_paths, 'find_framework_root', lambda: monorepo)
    fake_ssh = folder / 'ssh'
    fake_ssh.write_text('#!/bin/sh\nexec /bin/sleep 60\n')
    fake_ssh.chmod(0o700)
    parent = client.post('/api/term/sessions', json={'workspace_id': 'demo', 'kind': 'terminal'}).json()
    catalog = _save(client, 'demo', [
        {'label': 'Remote main', 'command': str(fake_ssh) + ' fixture'},
        {'label': 'Remote child', 'command': str(fake_ssh) + ' fixture'},
        {'label': 'Local child', 'command': 'sleep 60'},
    ], launch_delay_seconds=0)
    response = client.post('/api/term/automations/launch', json=_launch(client, parent, catalog))
    assert response.status_code == 200, response.text
    sessions = response.json()['sessions']
    assert len(sessions) == 3, response.text
    for session in sessions:
        _status(client, session['logical_name'], 'running')
    since = max(row['updated_at'] for row in lifecycle.read(folder).values())
    roots = [{'id': 'fixture', 'path': monorepo}]
    listing = lambda: term._tmux_list('lab-owned-', progress=True)
    assert reminders.check(roots, listing(), now=since + 1799)['changed'] == 0
    monkeypatch.setattr(supervisor.terminal_cleanup, '_roots', lambda root: roots)
    monitor = supervisor.Supervisor(now=since + 1680)
    result = monitor.tick(monorepo, now=since + 1800)
    assert result['automation_monitored'] == 1 and result['automation_reminders'] == 1 and not result['warnings']
    rows = client.get('/api/term/sessions', params={'workspace_id': 'demo'}).json()
    main = next(row for row in rows if row['name'] == parent['name'])
    first = main['terminal_automation_alert']
    assert first['active'] and main['terminal_status'] is None and main['llm_controlled'] is False
    assert all(not row['terminal_automation_alert'] for row in rows if row['name'] != main['name'])
    batch = client.get('/api/workspace-documents/attention').json()
    notice = next(row for rows in batch.values() for row in rows if row['name'] == main['name'])
    assert notice['terminal_automation_alert'] == first and notice['notification_context']['workspace']
    assert reminders.check(roots, listing(), now=since + 1801)['changed'] == 0, 'restart-safe deduplication'
    old = next(row for row in listing() if row['name'] == main['name'])
    assert reminders.check(roots, listing(), now=since + 3600)['changed'] == 1
    assert not reminders.persist(old, first), 'a stale scan cannot replace a newer reminder'
    for session in sessions[:2]:
        run('send-keys', '-t', session['name'], 'C-c')
        _status(client, session['logical_name'], 'stopped')
    assert reminders.check(roots, listing(), now=since + 3601)['changed'] == 1
    current = next(row for row in listing() if row['name'] == main['name'])
    assert not current['terminal_automation_alert']['active'], 'all remote connections ended'
    assert reminders.check(roots, listing(), now=since + 5400)['changed'] == 0
    run('kill-session', '-t', main['name'])
    run('new-session', '-d', '-s', main['name'], '/bin/sleep 60')
    assert not reminders.persist(current, first), 'recreated sessions do not inherit old reminders'
