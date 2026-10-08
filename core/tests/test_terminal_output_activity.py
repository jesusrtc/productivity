"""Output activity comes from the existing batched tmux listing."""
import shutil
import subprocess
import time
import uuid

import pytest

from core.routes import term


@pytest.mark.parametrize('cleanup_activity', [False, True])
@pytest.mark.parametrize('timestamp', ['100', '', 'unknown'])
def test_listing_adds_output_time_without_extra_commands(monkeypatch, cleanup_activity, timestamp):
    monkeypatch.setattr(term, '_tmux_available', lambda: True)
    monkeypatch.setattr(term.tmux_sockets, 'generations', lambda: [{'name':'default'}])
    calls = []

    def run(argv, **kwargs):
        calls.append(argv)
        values = ['neurona-fixture', '90', '0', '1', '/dev/fixture', '123']
        if cleanup_activity:
            values += ['99', '98', '97', '$1']
        values += ['%1', '0', '1', timestamp]
        return subprocess.CompletedProcess(argv, 0, stdout='|'.join(values)+'\n', stderr='')

    monkeypatch.setattr(term.subprocess, 'run', run)
    row, = term._tmux_list('neurona-', prune_draining=False, activity=cleanup_activity)
    assert len(calls) == 1 and 'list-sessions' in calls[0]
    assert '#{window_activity}' in calls[0][-1]
    assert row['pane_id'] == '%1' and row['pane_count'] == 1
    if timestamp == '100':
        assert row['output_activity']['updated_at'] == 100
        assert row['output_activity']['observed_at'] >= 100
    else:
        assert 'output_activity' not in row
    if cleanup_activity:
        assert row['activity'] == 99 and row['tmux_id'] == '$1'


def test_native_detached_output_changes_timestamp_but_selection_does_not(monkeypatch):
    if not shutil.which('tmux'):
        pytest.skip('tmux required')
    socket = 'lab-output-test-' + uuid.uuid4().hex[:12]
    monkeypatch.setattr(term.tmux_sockets, 'generations', lambda: [{'name':socket}])
    monkeypatch.setattr(term, '_tmux_available', lambda: True)

    def run(*args):
        return subprocess.run(['tmux', '-L', socket, *args], capture_output=True,
                              text=True, check=True, timeout=5)

    try:
        run('-f', '/dev/null', 'new-session', '-d', '-s', 'neurona-fixture',
            'sh -c "printf first; sleep 1.2; printf second; sleep 30"')
        first, = term._tmux_list('neurona-', prune_draining=False)
        initial = first['output_activity']['updated_at']
        deadline = time.monotonic() + 5
        while True:
            row, = term._tmux_list('neurona-', prune_draining=False)
            if row['output_activity']['updated_at'] > initial:
                break
            assert time.monotonic() < deadline, 'detached output did not update the timestamp'
            time.sleep(.05)
        assert row['created'] == first['created']
        assert row['output_activity']['observed_at'] >= row['output_activity']['updated_at']
        run('select-pane', '-t', 'neurona-fixture:0.0')
        selected, = term._tmux_list('neurona-', prune_draining=False)
        assert selected['output_activity']['updated_at'] == row['output_activity']['updated_at']
    finally:
        subprocess.run(['tmux', '-L', socket, 'kill-server'], capture_output=True, timeout=5)
