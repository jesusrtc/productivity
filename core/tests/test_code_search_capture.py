"""Capped search still waits for and decodes the complete command output."""
import os
import subprocess
import sys
import time

import pytest

from core.routes import code_search


@pytest.fixture
def owned_search(monkeypatch, tmp_path):
    native_run = subprocess.run
    monkeypatch.setattr(code_search.shutil, 'which', lambda _: '/owned/rg')

    def search(code, *args, limit=100, timeout=20.0):
        def run(command, **kwargs):
            assert command[0] == '/owned/rg' and command[-3:] == ['--', 'needle', '.']
            assert kwargs['cwd'] == str(tmp_path) and kwargs['timeout'] == 20.0
            return native_run([sys.executable, '-c', code, *args], **{**kwargs, 'timeout': timeout})

        monkeypatch.setattr(code_search.subprocess, 'run', run)
        return code_search._search_code(tmp_path, 'needle', limit)

    return search


def test_native_search_decodes_invalid_output_beyond_result_cap(owned_search):
    # Successful earlier rows must not hide a decoding failure later in stdout.
    with pytest.raises(UnicodeDecodeError):
        owned_search('import os; os.write(1,b"a.py:1:kept\\n\\xff")', limit=1)


def test_native_search_preserves_newlines_unicode_and_nonzero_exit(owned_search):
    assert owned_search(
        'import os; os.write(1,"a.py:1:café 中文\\r\\nb.py:2:tail\\r".encode()); '
        'os.write(2,b"diagnostic\\n"); raise SystemExit(2)',
    ) == {'mode': 'code', 'results': [
        {'path': 'a.py', 'line': 1, 'snippet': 'café 中文'},
        {'path': 'b.py', 'line': 2, 'snippet': 'tail'},
    ], 'truncated': False}


def test_native_timeout_reaps_child_and_discards_partial_results(tmp_path, owned_search):
    pid_file = tmp_path / 'owned.pid'
    result = owned_search(
        'import os,time,sys; from pathlib import Path; '
        'Path(sys.argv[1]).write_text(str(os.getpid())); '
        'os.write(1,b"a.py:1:partial\\n"); time.sleep(5)', str(pid_file), timeout=.5,
    )
    assert result == {'mode': 'code', 'results': [], 'truncated': True,
                      'error': 'search timed out (>20s) — try a more specific query'}
    with pytest.raises(ProcessLookupError):
        os.kill(int(pid_file.read_text()), 0)


@pytest.mark.skipif(not hasattr(os, 'fork'), reason='POSIX descendant-output check')
def test_search_waits_for_a_wrapper_descendants_stdout(tmp_path, owned_search):
    pid_file = tmp_path / 'owned-descendant.pid'
    try:
        result = owned_search(
            'import os,time,sys; from pathlib import Path\n'
            'pid=os.fork()\n'
            'if pid == 0:\n'
            ' os.close(2)\n'
            ' time.sleep(.2)\n'
            ' os.write(1,b"late.py:2:late\\n")\n'
            ' os._exit(0)\n'
            'Path(sys.argv[1]).write_text(str(pid))\n'
            'os.write(1,b"first.py:1:first\\n")\n'
            'os._exit(0)\n', str(pid_file),
        )
        assert result == {'mode': 'code', 'results': [
            {'path': 'first.py', 'line': 1, 'snippet': 'first'},
            {'path': 'late.py', 'line': 2, 'snippet': 'late'},
        ], 'truncated': False}
    finally:
        pid = int(pid_file.read_text())
        deadline = time.monotonic() + 5
        while True:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                break
            assert time.monotonic() < deadline, 'Owned descendant did not exit'
            time.sleep(.01)
