"""Terminal listings carry explicit status without capturing pane output."""
import subprocess
import pytest
from core.routes import term


@pytest.mark.parametrize('cleanup_activity', [False, True])
@pytest.mark.parametrize('timestamp', ['100', '', 'unknown'])
def test_listing_never_captures_output_to_estimate_status(monkeypatch, cleanup_activity, timestamp):
    monkeypatch.setattr(term, '_tmux_available', lambda: True)
    monkeypatch.setattr(term.tmux_sockets, 'generations', lambda: [{'name':'default'}])
    calls = []

    def run(argv, **kwargs):
        calls.append(argv)
        assert 'capture-pane' not in argv, 'listing must not infer state from output'
        values = ['neurona-fixture', '90', '0', '1', '/dev/fixture', '123']
        if cleanup_activity:
            values += ['99', '98', '97', '$1']
        values += ['%1', '0', '1', timestamp, '80', '24']
        return subprocess.CompletedProcess(argv, 0, stdout='|'.join(values)+'\n', stderr='')

    monkeypatch.setattr(term.subprocess, 'run', run)
    row, = term._tmux_list('neurona-', prune_draining=False, activity=cleanup_activity)
    assert len(calls) == 1, 'status listing never captures output to guess activity'
    assert 'list-sessions' in calls[0]
    assert '#{@lab_status}' in calls[0][-1]
    assert row['pane_id'] == '%1' and row['pane_count'] == 1
    assert row['terminal_status'] is None
    assert 'output_activity' not in row
    if cleanup_activity:
        assert row['activity'] == 99 and row['tmux_id'] == '$1'


@pytest.mark.parametrize('activity', [False, True])
@pytest.mark.parametrize('state', ['attention', 'finished', 'working'])
def test_listing_carries_latest_alert_in_same_batch(monkeypatch, activity, state):
    monkeypatch.setattr(term, '_tmux_available', lambda: True)
    monkeypatch.setattr(term.tmux_sockets, 'generations', lambda: [{'name':'default'}])
    status = {'version':1, 'state':'working', 'id':'a'*32, 'message':'New work', 'revision':20, 'updated_at':200}
    alert = {**status, 'id':'b'*32, 'state':state, 'message':'Previous alert', 'revision':10, 'updated_at':100}
    calls = []
    def run(argv, **kwargs):
        calls.append(argv)
        values = ['neurona-fixture', '90', '0', '1', '/dev/fixture', '123']
        if activity:
            values += ['99', '98', '97', '$1']
        values += ['%1', '0', '1', '100', '80', '24', term.terminal_status.encode(status), '$1', '1', term.terminal_status.encode(alert)]
        return subprocess.CompletedProcess(argv, 0, stdout='|'.join(values)+'\n', stderr='')
    monkeypatch.setattr(term.subprocess, 'run', run)
    row, = term._tmux_list('neurona-', prune_draining=False, activity=activity)
    assert len(calls) == 1 and '#{@lab_notification}' in calls[0][-1]
    assert row['terminal_status'] == status
    assert row['terminal_notification'] == (alert if state in ('attention', 'finished') else None)
