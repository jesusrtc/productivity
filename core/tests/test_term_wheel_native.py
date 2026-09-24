"""Real tmux command parsing and failure behavior on a private owned server."""
import os
import shutil
import subprocess
import tempfile
import time

import pytest


def test_wheel_batch_preserves_options_bindings_and_failure_recovery(monkeypatch):
    from core.routes import term
    tmux = shutil.which('tmux')
    if not tmux:
        pytest.skip('tmux is required')
    with tempfile.TemporaryDirectory(prefix='lab-wheel-', dir='/tmp') as directory:
        monkeypatch.setenv('TMUX_TMPDIR', directory)
        env = term._tmux_child_env()
        socket = 'owned-wheel'
        prefix = [tmux, '-L', socket]
        server_pid = None

        def run(*args, check=True):
            return subprocess.run([*prefix, *args], capture_output=True, text=True,
                                  env=env, check=check, timeout=10)

        def option(session, name):
            return run('show-options', '-v', '-t', session, name).stdout.strip()

        def bindings():
            return run('list-keys', '-T', 'root').stdout.splitlines()

        try:
            run('-f', '/dev/null', 'new-session', '-d', '-s', 'owned', '/bin/sleep 60')
            server_pid = int(run('display-message', '-p', '#{pid}').stdout)
            run('new-session', '-d', '-s', 'other', '/bin/sleep 60')
            run('set-option', '-t', 'owned', 'mouse', 'off')
            run('set-option', '-t', 'other', 'mouse', 'off')
            run('set-option', '-t', 'owned', 'alternate-screen', 'on')
            run('set-option', '-t', 'other', 'alternate-screen', 'on')
            run('bind-key', '-T', 'root', 'WheelDownPane', 'display-message', 'old binding')
            term._configure_tmux_wheel_scrolling('owned', socket)
            assert option('owned', 'mouse') == 'on'
            assert option('owned', 'alternate-screen') == 'off'
            assert option('other', 'mouse') == 'off'
            assert option('other', 'alternate-screen') == 'on'
            up = next(row for row in bindings() if 'WheelUpPane ' in row)
            assert '#{||:#{pane_in_mode},#{mouse_any_flag}}' in up
            assert 'send-keys -M' in up and 'copy-mode -e' in up
            assert 'alternate_on' not in up and 'copy-mode -eu' not in up
            assert not any('WheelDownPane ' in row for row in bindings())
            # A session can exit between spawn and configuration. A failing
            # first option must still leave both server-global bindings correct.
            run('unbind-key', '-T', 'root', 'WheelUpPane')
            run('bind-key', '-T', 'root', 'WheelDownPane', 'display-message', 'old binding')
            term._configure_tmux_wheel_scrolling('missing-session', socket)
            assert next(row for row in bindings() if 'WheelUpPane ' in row) == up
            assert not any('WheelDownPane ' in row for row in bindings())
            assert option('other', 'mouse') == 'off'
            assert option('other', 'alternate-screen') == 'on'
        finally:
            run('kill-server', check=False)
            assert run('list-sessions', check=False).returncode != 0
            if server_pid is not None:
                deadline = time.monotonic() + 3
                while True:
                    try:
                        os.kill(server_pid, 0)
                    except ProcessLookupError:
                        break
                    assert time.monotonic() < deadline, 'Owned tmux server did not exit'
                    time.sleep(.01)
