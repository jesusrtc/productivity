"""Native binary capture must equal subprocess text-mode results and failures."""
import hashlib
import json
import os
import subprocess
import sys
from types import SimpleNamespace

import pytest

from core.routes import code_search


def _outcome(call):
    try:
        proc = call()
        return 'result', proc.args, proc.returncode, proc.stdout, proc.stderr
    except UnicodeDecodeError as error:
        return ('decode-error', error.encoding, len(error.object),
                hashlib.sha256(error.object).hexdigest(), error.start, error.end, error.reason)


@pytest.mark.skipif(os.name != 'posix', reason='POSIX binary-capture encoding path')
@pytest.mark.parametrize('encoding', ['utf-8', 'ascii', 'latin-1', 'utf-16-le'])
@pytest.mark.parametrize('kind', ['empty', 'newlines', 'large', 'bad-stdout', 'bad-stderr', 'bad-both'])
@pytest.mark.parametrize('returncode', [0, 2])
def test_native_capture_equals_text_mode(monkeypatch, tmp_path, encoding, kind, returncode):
    # Patch only this module's encoding providers, not the interpreter's locale.
    monkeypatch.setattr(code_search, 'io', SimpleNamespace(text_encoding=lambda _: 'locale'))
    monkeypatch.setattr(code_search, 'locale', SimpleNamespace(getencoding=lambda: encoding))
    text = 'a.py:1:cafe\nb.py:2:tail\n'
    if encoding != 'ascii':
        text += 'c.py:3:café\n'
    stdout = text.encode(encoding)
    stderr = 'diagnostic\r\nsecond\rlast\n'.encode(encoding)
    if kind == 'empty':
        stdout = stderr = b''
    elif kind == 'newlines':
        stdout = ('a.py:1:a\r\nb.py:2:b\rc.py:3:c\n\r\r\n').encode(encoding)
    elif kind == 'large':
        stdout *= 50_000
        stderr *= 10_000
    else:
        if kind in {'bad-stdout', 'bad-both'}:
            stdout += b'\xff'
        if kind in {'bad-stderr', 'bad-both'}:
            stderr += b'\xfe'
    output_file, error_file = tmp_path / 'stdout.bin', tmp_path / 'stderr.bin'
    output_file.write_bytes(stdout)
    error_file.write_bytes(stderr)
    command = [sys.executable, '-c',
        'import sys; from pathlib import Path; '
        'sys.stdout.buffer.write(Path(sys.argv[1]).read_bytes()); '
        'sys.stderr.buffer.write(Path(sys.argv[2]).read_bytes()); '
        'raise SystemExit(int(sys.argv[3]))', str(output_file), str(error_file), str(returncode)]
    expected = _outcome(lambda: subprocess.run(
        command, cwd=str(tmp_path), capture_output=True, text=True, encoding=encoding, timeout=20.0))
    actual = _outcome(lambda: code_search._capture_search_output(command, tmp_path))
    assert actual == expected


@pytest.mark.skipif(os.name != 'posix', reason='POSIX binary-capture encoding path')
def test_encoding_is_selected_before_the_command_and_is_not_cached(monkeypatch, tmp_path):
    selected = {'encoding': 'latin-1'}
    events = []
    monkeypatch.setattr(code_search, 'io', SimpleNamespace(text_encoding=lambda _: 'locale'))

    def encoding():
        events.append('encoding')
        return selected['encoding']

    def run(command, **kwargs):
        events.append('run')
        selected['encoding'] = 'ascii'
        assert kwargs == {'cwd': str(tmp_path), 'capture_output': True, 'text': False, 'timeout': 20.0}
        return subprocess.CompletedProcess(command, 0, b'caf\xe9\r\n', b'')

    monkeypatch.setattr(code_search, 'locale', SimpleNamespace(getencoding=encoding))
    monkeypatch.setattr(code_search.subprocess, 'run', run)
    assert code_search._capture_search_output(['/owned/rg'], tmp_path).stdout == 'café\n'
    with pytest.raises(UnicodeDecodeError):
        code_search._capture_search_output(['/owned/rg'], tmp_path)
    assert events == ['encoding', 'run', 'encoding', 'run']


def test_non_posix_capture_keeps_original_text_mode(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(code_search, 'os', SimpleNamespace(name='nt'))

    def encoding(*args):
        raise AssertionError('The original text-mode runner selects its own encoding')

    monkeypatch.setattr(code_search, 'io', SimpleNamespace(text_encoding=encoding))

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 2, 'a.py:1:kept\n', 'diagnostic\n')

    monkeypatch.setattr(code_search.subprocess, 'run', run)
    command = ['/owned/rg', '--', 'needle', '.']
    proc = code_search._capture_search_output(command, tmp_path)
    assert (proc.returncode, proc.stdout, proc.stderr) == (2, 'a.py:1:kept\n', 'diagnostic\n')
    assert calls == [(command, {'cwd': str(tmp_path), 'capture_output': True, 'text': True, 'timeout': 20.0})]


@pytest.mark.parametrize('utf8_mode', [0, 1])
@pytest.mark.parametrize('warn_default', [0, 1])
def test_native_default_encoding_and_warning_flags(tmp_path, utf8_mode, warn_default):
    script = r'''
import json,sys,subprocess,warnings
from pathlib import Path
from core.routes.code_search import _capture_search_output
command=[sys.executable,'-c',"import os; os.write(1,bytes.fromhex('636166c3a90d0a')); os.write(2,b'diagnostic\\r\\n')"]
results=[]
for capture in [lambda:subprocess.run(command,cwd=sys.argv[1],capture_output=True,text=True,timeout=20),
                lambda:_capture_search_output(command,Path(sys.argv[1]))]:
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter('always',EncodingWarning)
        try:
            result=capture()
            outcome=['ok',result.returncode,result.stdout,result.stderr]
        except UnicodeDecodeError as error:
            outcome=['error',error.encoding,error.object.hex(),error.start,error.end,error.reason]
        results.append([outcome,[warning.category.__name__ for warning in captured]])
print(json.dumps(results))
'''
    environment = os.environ.copy()
    environment.pop('PYTHONWARNDEFAULTENCODING', None)
    proc = subprocess.run([
        sys.executable, f'-Xutf8={utf8_mode}', *(['-Xwarn_default_encoding'] if warn_default else []),
        '-c', script, str(tmp_path),
    ], capture_output=True, text=True, timeout=20, env=environment)
    assert proc.returncode == 0, proc.stderr
    original, candidate = json.loads(proc.stdout)
    assert candidate == original
    assert candidate[1] == (['EncodingWarning'] if warn_default else [])
