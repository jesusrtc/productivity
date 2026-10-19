import pytest

from core import terminal_progress as supervisor
from core.routes import term
from lab import terminal_progress as progress, terminal_status


def row(at=100, identity='a'):
    report = {'version': 1, 'state': 'working', 'id': identity * 32, 'message': 'Running checks',
              'updated_at': at, 'revision': int(at * 1000)}
    return {'name': 'lab-owned-one', 'created': 90, 'tmux_id': '$1', 'tmux_socket': 'owned',
            'pane_pid': 42, 'terminal_status': report, 'llm_controlled': True,
            '_progress_status_token': terminal_status.encode(report),
            '_progress_hook_token': '', '_progress_alert_token': ''}


@pytest.fixture
def setup(monkeypatch, tmp_path):
    rows, writes = [row()], []
    monkeypatch.setattr(supervisor.terminal_cleanup, '_roots', lambda root: [])
    monkeypatch.setattr(term, '_tmux_discovery_prefixes_all', lambda roots: ['lab-owned-'])
    monkeypatch.setattr(term, '_tmux_list', lambda *a, **k: rows)
    monkeypatch.setattr(supervisor, 'agent_presence', lambda rows: {})
    def persist(current, alert):
        writes.append(alert)
        current['_progress_alert_token'] = terminal_status.encode(alert)
        return True
    monkeypatch.setattr(supervisor, 'persist', persist)
    return supervisor.Supervisor(now=1780), rows, writes, tmp_path


def test_one_alert_per_report_resolves_without_browser_and_survives_restart(setup):
    monitor, rows, writes, root = setup
    assert monitor.tick(root, now=1899)['new_alerts'] == 0
    assert monitor.tick(root, now=1900)['new_alerts'] == 1
    monitor.tick(root, now=1960)
    assert len(writes) == 1
    restarted = supervisor.Supervisor(now=1961)
    restarted.tick(root, now=2081)
    assert len(writes) == 1, 'retained tmux alert deduplicates across backend restarts'
    assert rows[0]['terminal_status']['state'] == 'working'
    previous = progress.decode(rows[0]['_progress_alert_token'])
    rows[0].update(row(at=2082, identity='b'))
    assert not progress.view(rows[0]['terminal_status'], {}, previous)['alert']['active']


def test_resume_grace_does_not_reset_the_actual_report_clock(setup):
    monitor, rows, writes, root = setup
    assert monitor.tick(root, now=10000)['new_alerts'] == 0
    assert monitor.grace_until == 10120
    assert monitor.tick(root, now=10119)['new_alerts'] == 0
    assert monitor.tick(root, now=10120)['new_alerts'] == 1
    assert rows[0]['terminal_status']['updated_at'] == 100


@pytest.mark.parametrize('state', ['attention', 'finished', 'disabled'])
def test_ineligible_sessions_are_excluded(setup, state):
    monitor, rows, writes, root = setup
    if state == 'disabled':
        rows[0]['llm_controlled'] = False
    else:
        rows[0]['terminal_status']['state'] = state
    assert monitor.tick(root, now=1900)['monitored'] == 0
    assert not writes


def test_stopped_process_needs_prior_running_and_two_successful_absences(setup, monkeypatch):
    monitor, rows, writes, root = setup
    rows[0].update(row(at=1800))
    key = ('owned', '$1', 90)
    presence = {key: False}
    monkeypatch.setattr(supervisor, 'agent_presence', lambda rows: presence)
    monitor.tick(root, now=1900)
    monitor.tick(root, now=1960)
    assert not writes, 'a marker alone is not proof the process was running'
    presence[key] = True
    monitor.tick(root, now=2020)
    presence[key] = False
    monitor.tick(root, now=2080)
    presence[key] = None
    monitor.tick(root, now=2140)
    presence[key] = False
    monitor.tick(root, now=2200)
    assert not writes, 'unknown reads interrupt consecutive missing observations'
    monitor.tick(root, now=2260)
    assert len(writes) == 1 and writes[0]['kind'] == 'exited'


def test_failed_listing_does_not_mutate_reports(setup, monkeypatch):
    monitor, rows, writes, root = setup
    monkeypatch.setattr(term, '_tmux_list', lambda *a, **k: None)
    with pytest.raises(supervisor.HTTPException) as error:
        monitor.tick(root, now=1900)
    assert error.value.status_code == 503 and not writes


def test_presence_is_pane_scoped_and_unknown_is_not_stopped(monkeypatch):
    rows = [row(), {**row(), 'tmux_id': '$2', 'pane_pid': 99}]
    snapshot = {42: {'ppid': 1, 'stat': 'S', 'comm': 'zsh'},
                43: {'ppid': 42, 'stat': 'S', 'comm': 'copilot'}}
    monkeypatch.setattr(supervisor.terminal_llm, 'processes', lambda candidates: snapshot)
    result = supervisor.agent_presence(rows)
    assert result[('owned', '$1', 90)] is True
    assert result[('owned', '$2', 90)] is None
    snapshot[43]['stat'] = 'Z'
    assert supervisor.agent_presence(rows)[('owned', '$1', 90)] is False
