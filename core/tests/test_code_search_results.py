"""Capped search parsing retains both backends' complete response semantics."""
from pathlib import Path
import subprocess

import pytest

from core.routes import code_search


BOUNDARIES = ['\n', '\r', '\r\n', '\v', '\f', '\x1c', '\x1d', '\x1e', '\x85', '\u2028', '\u2029']


@pytest.mark.parametrize('backend', ['rg', 'git'])
@pytest.mark.parametrize('boundary', BOUNDARIES)
@pytest.mark.parametrize('limit', [1, 3, 4, 500])
def test_capped_results_preserve_boundaries_order_numbers_and_snippets(monkeypatch, backend, boundary, limit):
    output = boundary.join([
        '', 'Binary file ./ignored.bin matches', 'not a result', 'bad.py:nan:skip',
        './a.py:1:first:with:colons', '', 'b.py:+02:café 中文',
        '././nested.py:-3:' + 'é' * 320, 'invalid:path:5:skip',
        'empty.py:4:', '',
    ])
    calls = []
    monkeypatch.setattr(code_search.shutil, 'which', lambda _: '/owned/rg' if backend == 'rg' else None)

    def rg(command, repo_dir):
        calls.append(command)
        assert repo_dir == Path('/owned/repo')
        return subprocess.CompletedProcess(command, 0, output, '')

    def git(root, args, timeout):
        calls.append(args)
        assert root == Path('/owned/repo') and timeout == 20.0
        return 0, output, ''

    monkeypatch.setattr(code_search, '_capture_search_output', rg)
    monkeypatch.setattr(code_search, '_git', git)
    actual = code_search._search_code(Path('/owned/repo'), '--query', limit)
    expected = [
        {'path': 'a.py', 'line': 1, 'snippet': 'first:with:colons'},
        {'path': 'b.py', 'line': 2, 'snippet': 'café 中文'},
        {'path': './nested.py', 'line': -3, 'snippet': 'é' * 300},
        {'path': 'empty.py', 'line': 4, 'snippet': ''},
    ]
    assert actual == {'mode': 'code', 'results': expected[:limit], 'truncated': limit <= len(expected)}
    assert len(calls) == 1
    tail = ['--', '--query', '.'] if backend == 'rg' else ['--', '--query']
    assert calls[0][-len(tail):] == tail


@pytest.mark.parametrize('backend', ['rg', 'git'])
@pytest.mark.parametrize('returncode', [0, 1, 2, 124])
@pytest.mark.parametrize('output', ['', '\n\r\v\f\x85\u2028', 'bad\nwrong:nan:line\n'])
def test_empty_or_invalid_output_keeps_existing_error_handling(monkeypatch, backend, returncode, output):
    monkeypatch.setattr(code_search.shutil, 'which', lambda _: '/owned/rg' if backend == 'rg' else None)
    monkeypatch.setattr(code_search, '_capture_search_output', lambda command, repo_dir:
                        subprocess.CompletedProcess(command, returncode, output, 'tool diagnostic'))
    monkeypatch.setattr(code_search, '_git', lambda *args, **kwargs: (returncode, output, 'tool diagnostic'))
    assert code_search._search_code(Path('/owned/repo'), 'needle', 100) == {
        'mode': 'code', 'results': [], 'truncated': False,
    }


def test_rg_timeout_still_discards_partial_output(monkeypatch):
    monkeypatch.setattr(code_search.shutil, 'which', lambda _: '/owned/rg')

    def timeout(command, repo_dir):
        raise subprocess.TimeoutExpired(command, 20, output='a.py:1:partial\n')

    monkeypatch.setattr(code_search, '_capture_search_output', timeout)
    assert code_search._search_code(Path('/owned/repo'), 'needle', 100) == {
        'mode': 'code', 'results': [], 'truncated': True,
        'error': 'search timed out (>20s) — try a more specific query',
    }


def test_parser_does_not_materialize_unused_output_lines(monkeypatch):
    class SearchOutput(str):
        def splitlines(self, *args, **kwargs):
            raise AssertionError('Capped search must not split the entire output')

    output = SearchOutput('first.py:1:kept\n' + 'later.py:2:unused\n' * 10_000)
    monkeypatch.setattr(code_search.shutil, 'which', lambda _: '/owned/rg')
    monkeypatch.setattr(code_search, '_capture_search_output', lambda command, repo_dir:
                        subprocess.CompletedProcess(command, 0, output, ''))
    assert code_search._search_code(Path('/owned/repo'), 'needle', 1) == {
        'mode': 'code', 'results': [{'path': 'first.py', 'line': 1, 'snippet': 'kept'}],
        'truncated': True,
    }
