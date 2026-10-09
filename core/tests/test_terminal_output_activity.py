"""Terminal activity requires a verified content change, not raw tmux I/O."""
import os
import re
import shlex
import shutil
import subprocess
import time
import uuid

import pytest

from core.routes import term
from core import terminal_output_activity as activity


@pytest.fixture(autouse=True)
def isolated_activity_cache(monkeypatch):
    monkeypatch.setattr(activity, '_states', {})


@pytest.mark.parametrize('cleanup_activity', [False, True])
@pytest.mark.parametrize('timestamp', ['100', '', 'unknown'])
def test_listing_verifies_content_and_keeps_cleanup_cheap(monkeypatch, cleanup_activity, timestamp):
    monkeypatch.setattr(term, '_tmux_available', lambda: True)
    monkeypatch.setattr(term.tmux_sockets, 'generations', lambda: [{'name':'default'}])
    calls = []

    def run(argv, **kwargs):
        calls.append(argv)
        if 'capture-pane' in argv:
            markers = [arg for arg in argv if re.fullmatch(r'lab-content-[0-9a-f]+:\d+', arg)]
            return subprocess.CompletedProcess(argv, 0, stdout=markers[0]+'\nexisting output\n'+markers[1]+'\n', stderr='')
        values = ['neurona-fixture', '90', '0', '1', '/dev/fixture', '123']
        if cleanup_activity:
            values += ['99', '98', '97', '$1']
        values += ['%1', '0', '1', timestamp, '80', '24']
        return subprocess.CompletedProcess(argv, 0, stdout='|'.join(values)+'\n', stderr='')

    monkeypatch.setattr(term.subprocess, 'run', run)
    row, = term._tmux_list('neurona-', prune_draining=False, activity=cleanup_activity)
    assert len(calls) == (2 if timestamp == '100' and not cleanup_activity else 1)
    assert 'list-sessions' in calls[0]
    assert '#{window_activity}' in calls[0][-1]
    assert row['pane_id'] == '%1' and row['pane_count'] == 1
    if timestamp == '100' and not cleanup_activity:
        assert row['output_activity']['version'] == 2
        assert row['output_activity']['updated_at'] == 0, 'existing content is a baseline, not work'
        assert row['output_activity']['observed_at'] >= 100
    else:
        assert 'output_activity' not in row
    if cleanup_activity:
        assert row['activity'] == 99 and row['tmux_id'] == '$1'


def test_content_hash_ignores_padding_but_keeps_meaningful_changes():
    assert activity._fingerprint('ready\n\n  \n') == activity._fingerprint('ready \n')
    assert activity._fingerprint(' ready\n') != activity._fingerprint('ready\n')
    assert activity._fingerprint('ready\nready\n') != activity._fingerprint('ready\n')


def test_raw_noise_baseline_resize_and_real_output(monkeypatch):
    clock = [200.0]
    content = ['ready']
    calls = []
    monkeypatch.setattr(activity.time, 'time', lambda: clock[0])

    def capture(socket, panes, env):
        calls.append(panes)
        return {pane: activity._fingerprint(content[0]) for pane in panes}

    monkeypatch.setattr(activity, '_capture_batch', capture)

    def sample(raw, geometry=(80, 24)):
        row = {'pane_id':'%1', 'created':90, 'pane_pid':123}
        activity.enrich('fixture', [(row, raw, geometry)], env={})
        return row['output_activity']

    assert sample(100)['updated_at'] == 0
    assert sample(100)['updated_at'] == 0 and len(calls) == 1, 'idle polling does not capture again'
    assert sample(150)['updated_at'] == 0, 'OSC/title/control-only output is not work'
    content[0] = 'ready\nnew result'
    result = sample(180)
    assert result['updated_at'] == 180
    content[0] = 'reflowed viewport\nnew result'
    assert sample(190, (100, 30))['updated_at'] == 180, 'a resize establishes a fresh screen baseline'
    assert sample(195, (100, 30))['updated_at'] == 180, 'unchanged redraws cannot reset quiet time'
    content[0] += '\nactual next output'
    assert sample(199, (100, 30))['updated_at'] == 199
    row = {'pane_id':'%1', 'created':90, 'pane_pid':124}
    activity.enrich('fixture', [(row, 199, (100, 30))], env={})
    assert row['output_activity']['updated_at'] == 0, 'a replaced process starts with a new baseline'
    assert row['output_activity']['generation'] != result['generation']


def test_final_output_in_same_timestamp_second_is_not_missed(monkeypatch):
    clock, content = [200.1], ['initial']
    calls = []
    monkeypatch.setattr(activity.time, 'time', lambda: clock[0])
    def capture(socket, panes, env):
        calls.append(panes)
        return {pane: activity._fingerprint(content[0]) for pane in panes}
    monkeypatch.setattr(activity, '_capture_batch', capture)
    def sample():
        row = {'pane_id':'%1', 'created':90, 'pane_pid':123}
        activity.enrich('fixture', [(row, 200, (80, 24))], env={})
        return row['output_activity']['updated_at']
    assert sample() == 0
    clock[0], content[0] = 200.3, 'working'
    assert sample() == 200
    clock[0], content[0] = 201.1, 'finished'
    assert sample() > 200
    sample()
    assert len(calls) == 3, 'once the raw timestamp second closes, unchanged polling is free'


def test_capture_failure_retains_unknown_state_and_retries(monkeypatch):
    monkeypatch.setattr(activity.time, 'time', lambda: 200)
    result = [{'\u00251':activity._fingerprint('ready')}]
    monkeypatch.setattr(activity, '_capture_batch', lambda *args: result[0])
    def sample(raw):
        row = {'pane_id':'%1', 'created':90, 'pane_pid':123}
        activity.enrich('fixture', [(row, raw, (80, 24))], env={})
        return row
    result[0] = {}
    assert 'output_activity' not in sample(100)
    result[0] = {'%1':activity._fingerprint('ready')}
    assert sample(100)['output_activity']['updated_at'] == 0
    result[0] = {}
    assert 'output_activity' not in sample(150), 'failed verification is not fresh quiet evidence'
    result[0] = {'%1':activity._fingerprint('new output')}
    assert sample(150)['output_activity']['updated_at'] == 150


def test_multiple_panes_share_one_capture_command_and_only_hashes_survive(monkeypatch):
    calls = []
    def run(argv, **kwargs):
        calls.append(argv)
        markers = [arg for arg in argv if re.fullmatch(r'lab-content-[0-9a-f]+:\d+', arg)]
        output = ''.join(marker+'\nprivate pane output\n' for marker in markers[:-1]) + markers[-1]+'\n'
        return subprocess.CompletedProcess(argv, 0, stdout=output, stderr='')
    monkeypatch.setattr(activity.subprocess, 'run', run)
    rows = [{'pane_id':f'%{i}', 'created':90, 'pane_pid':123+i} for i in range(20)]
    candidates = [(row, 100, (80, 24)) for row in rows]
    activity.enrich('fixture', candidates, env={})
    activity.enrich('fixture', candidates, env={})
    assert len(calls) == 1 and calls[0].count('capture-pane') == 20
    assert all(row['output_activity']['updated_at'] == 0 for row in rows)
    assert 'private pane output' not in repr(activity._states) + repr(rows)


def test_native_detached_noise_does_not_start_activity_but_real_content_does(monkeypatch, tmp_path):
    if not shutil.which('tmux'):
        pytest.skip('tmux required')
    socket = 'lab-output-test-' + uuid.uuid4().hex[:12]
    monkeypatch.setattr(term.tmux_sockets, 'generations', lambda: [{'name':socket}])
    monkeypatch.setattr(term, '_tmux_available', lambda: True)

    def run(*args):
        return subprocess.run(['tmux', '-L', socket, *args], capture_output=True,
                              text=True, check=True, timeout=5)

    try:
        fifo = tmp_path/'input'
        os.mkfifo(fifo)
        script = tmp_path/'writer.py'
        script.write_text('import sys, tty\ntty.setraw(sys.stdin.fileno())\nprint("ready",end="",flush=True)\n'
                          'with open(sys.argv[1],"rb",buffering=0) as f:\n while True:\n'
                          '  data=f.read(1024)\n  if not data: break\n'
                          '  sys.stdout.buffer.write(data); sys.stdout.buffer.flush()\n')
        run('-f', '/dev/null', 'new-session', '-d', '-s', 'neurona-fixture',
            shlex.join([os.sys.executable, str(script), str(fifo)]))
        run('new-session', '-d', '-s', 'neurona-sibling', 'printf sibling; sleep 30')
        with open(fifo, 'wb', buffering=0) as stream:
            time.sleep(.1)
            def sample():
                rows = term._tmux_list('neurona-', prune_draining=False)
                assert len(rows) == 2, 'native batch frames both panes correctly'
                row = next(row for row in rows if row['name'] == 'neurona-fixture')
                sibling = next(row for row in rows if row['name'] == 'neurona-sibling')
                assert sibling['output_activity']['updated_at'] == 0, 'an idle sibling stays quiet'
                return row['output_activity']['updated_at']
            def write(data):
                time.sleep(1.05)  # tmux's raw timestamp has second precision
                stream.write(data)
                time.sleep(.1)
            assert sample() == 0
            initial = run('display-message','-p','-t','neurona-fixture','#{window_activity}')
            for noise in [b'\x1b]0;ssh title\x07', b'\x1b[6n', b'\rready\x1b[K', b'\x1b[?25l\x1b[?25h']:
                write(noise)
                assert sample() == 0, 'invisible SSH/TUI I/O must not create yellow or green'
            assert run('display-message','-p','-t','neurona-fixture','#{window_activity}') != initial
            write(b' new output')
            changed = sample()
            assert changed > 0, 'real detached output starts activity'
            write(b'\x1b]0;another idle title\x07')
            assert sample() == changed, 'noise cannot restart an existing quiet period'
            run('select-pane', '-t', 'neurona-fixture:0.0')
            run('resize-window', '-t', 'neurona-fixture', '-x', '90', '-y', '30')
            assert sample() == changed
    finally:
        subprocess.run(['tmux', '-L', socket, 'kill-server'], capture_output=True, timeout=5)
