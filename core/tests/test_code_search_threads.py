"""Literal-search worker tuning preserves regex and configured tool behavior."""
from pathlib import Path
import shutil
import subprocess

import pytest

from core.routes import code_search


@pytest.fixture
def mac_many_cores(monkeypatch):
    monkeypatch.setattr(code_search.sys, 'platform', 'darwin')
    monkeypatch.setattr(code_search.os, 'cpu_count', lambda: 12)
    monkeypatch.delenv('RIPGREP_CONFIG_PATH', raising=False)


@pytest.mark.parametrize('query', ['needle', 'leading_option', 'café 中文', 'a/b:c d', '123_foo99', ''])
def test_mac_literal_search_bounds_workers(mac_many_cores, query):
    assert code_search._rg_thread_options(query) == ['--threads', '2']


@pytest.mark.parametrize('symbol', list('\\.^$*+?{}[]|()#&~-'))
def test_possible_regex_retains_tool_parallelism(mac_many_cores, symbol):
    assert code_search._rg_thread_options('before' + symbol + 'after') == []


@pytest.mark.parametrize('query', [r'foo\.bar', '(?i)needle', '[invalid', 'foo|bar', '^$', r'\p{L}+', r'\Qfoo\E'])
def test_regex_syntax_is_not_reinterpreted(mac_many_cores, query):
    assert code_search._rg_thread_options(query) == []


@pytest.mark.parametrize('platform', ['linux', 'win32', 'freebsd14'])
def test_other_platforms_keep_existing_arguments(monkeypatch, mac_many_cores, platform):
    monkeypatch.setattr(code_search.sys, 'platform', platform)
    assert code_search._rg_thread_options('needle') == []


@pytest.mark.parametrize('cores', [None, 1, 2, 4])
def test_never_increases_existing_small_machine_parallelism(monkeypatch, mac_many_cores, cores):
    monkeypatch.setattr(code_search.os, 'cpu_count', lambda: cores)
    assert code_search._rg_thread_options('needle') == []


def test_ripgrep_config_is_respected_and_read_afresh(monkeypatch, mac_many_cores):
    assert code_search._rg_thread_options('needle') == ['--threads', '2']
    monkeypatch.setenv('RIPGREP_CONFIG_PATH', '/owned/config with spaces')
    assert code_search._rg_thread_options('needle') == []
    monkeypatch.setenv('RIPGREP_CONFIG_PATH', '')
    assert code_search._rg_thread_options('needle') == ['--threads', '2']


@pytest.mark.parametrize('query,options', [('needle', ['--threads', '2']), ('n.*e', [])])
def test_search_retains_every_other_argument_and_capture_option(monkeypatch, mac_many_cores, query, options):
    calls = []
    monkeypatch.setattr(code_search.shutil, 'which', lambda _: '/owned/wrapper rg')

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, 'file.py:1:match\n', '')

    monkeypatch.setattr(code_search.subprocess, 'run', run)
    assert code_search._search_code(Path('/owned/repo'), query, 100) == {
        'mode': 'code', 'results': [{'path': 'file.py', 'line': 1, 'snippet': 'match'}], 'truncated': False,
    }
    assert calls == [(['/owned/wrapper rg', *options, '--max-count', '20', '--max-columns', '300',
                      '-n', '--no-heading', '--color', 'never', '--', query, '.'],
                     {'cwd': '/owned/repo', 'capture_output': True, 'text': True, 'timeout': 20.0})]


@pytest.mark.skipif(shutil.which('rg') is None, reason='Native ripgrep equivalence check')
@pytest.mark.parametrize('configured', [False, True])
def test_native_results_keep_ignore_unicode_regex_and_config_semantics(monkeypatch, mac_many_cores, tmp_path, configured):
    (tmp_path / '.git').mkdir()
    (tmp_path / '.gitignore').write_text('ignored.txt\n')
    (tmp_path / 'ignored.txt').write_text('needle ignored\n')
    (tmp_path / '.hidden.txt').write_text('needle hidden\n')
    for number in range(30 if configured else 20):
        (tmp_path / f'source-{number:02}.txt').write_text(
            'needle café 中文\nNEEDLE upper\nother\n' * 20)
    options = code_search._rg_thread_options
    if configured:
        config = tmp_path / '.git' / 'rg-config'
        config.write_text('--threads=1\n--sort=path\n--ignore-case\n')
        monkeypatch.setenv('RIPGREP_CONFIG_PATH', str(config))
    for query in ['café 中文', 'needle', 'n.*e', '[invalid']:
        monkeypatch.setattr(code_search, '_rg_thread_options', lambda _: [])
        original = code_search._search_code(tmp_path, query, 500)
        monkeypatch.setattr(code_search, '_rg_thread_options', options)
        candidate = code_search._search_code(tmp_path, query, 500)
        assert len(candidate['results']) == (0 if query == '[invalid' else 500 if configured else 400)
        assert candidate['mode'] == original['mode'] == 'code'
        assert candidate['truncated'] == original['truncated']
        if configured:
            # Explicit sort order and configured case folding stay authoritative.
            assert candidate == original
        elif not original['truncated']:
            assert sorted(candidate['results'], key=str) == sorted(original['results'], key=str)
        else:
            assert len(candidate['results']) == len(original['results']) == 500
            assert len({(row['path'], row['line']) for row in candidate['results']}) == 500
        for row in candidate['results']:
            assert row['path'].startswith('source-')
            assert 1 <= row['line'] <= 60 and row['line'] % 3 in {1, 2}
            assert row['snippet'] == ('needle café 中文' if row['line'] % 3 == 1 else 'NEEDLE upper')
