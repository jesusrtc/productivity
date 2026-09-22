"""The indexed cold lookup preserves old and new provider-schema behavior."""
import random
import sqlite3
import subprocess
from contextlib import closing

import pytest


@pytest.mark.parametrize('seed', range(24))
def test_indexed_snapshot_lookup_matches_fallback_for_mixed_processes(
    tmp_path, monkeypatch, seed,
):
    from core.routes import term

    monkeypatch.setenv('HOME', str(tmp_path))
    home = tmp_path / '.codex'
    home.mkdir()
    randomizer = random.Random(seed)
    with closing(sqlite3.connect(home / 'state_5.sqlite')) as conn:
        conn.execute('''CREATE TABLE threads (
            id TEXT, title TEXT, name TEXT, preview TEXT, archived INTEGER,
            source TEXT, cwd TEXT, updated_at INTEGER)''')
        conn.executemany('INSERT INTO threads VALUES (?,?,?,?,?,?,?,?)', [
            (f'thread-{i}', f'Title {i}' if i % 3 else '',
             'Generated name' if i % 4 == 0 else None,
             f'Preview {i}', int(i == 8), 'api' if i == 9 else 'cli', '/repo', i)
            for i in range(10)
        ])
        conn.commit()
    with closing(sqlite3.connect(home / 'logs_2.sqlite')) as conn:
        conn.execute('''CREATE TABLE logs (
            id INTEGER PRIMARY KEY, ts_nanos INTEGER DEFAULT 0,
            process_uuid TEXT, thread_id TEXT, ts INTEGER, target TEXT)''')
        # Several native processes can share one TTY; a PID may have multiple
        # historical UUIDs. Unknown/untitled threads and tied timestamps must
        # preserve the same winning conversation, not just the same row count.
        rows = [(f'pid:{pid}:{generation}', f'thread-{thread}',
                 randomizer.randrange(1, 30),
                 randomizer.choice(['codex_core::shell_snapshot', 'other']))
                for pid in (100, 101, 200, 999)
                for generation in ('old', 'new')
                for thread in range(14)
                for _ in range(3)]
        rows += [('unrecognized', 'thread-0', 99, 'codex_core::shell_snapshot'),
                 ('pid:100:new', None, 100, 'codex_core::shell_snapshot')]
        rows += [('pid:999:noise', 'thread-0', 100, 'other')] * 1500
        randomizer.shuffle(rows)
        conn.executemany('INSERT INTO logs (process_uuid,thread_id,ts,target) VALUES (?,?,?,?)', rows)
        conn.execute('CREATE INDEX idx_logs_ts ON logs(ts DESC, ts_nanos DESC, id DESC)')
        conn.commit()
    monkeypatch.setattr(term.subprocess, 'run', lambda *a, **kw:
                        subprocess.CompletedProcess([], 0, stdout=
                            '100 ttys001\n101 ttys001\n200 ttys002\n300 ttys003\n'))
    monkeypatch.setattr(term, '_CODEX_METADATA_CACHE', None)
    expected = term._codex_session_metadata_by_tty(
        {'ttys001', '/dev/ttys002', 'ttys003'}, {'/repo'})
    assert set(expected) == {'ttys001', 'ttys002'}
    with closing(sqlite3.connect(home / 'logs_2.sqlite')) as conn:
        conn.execute('CREATE INDEX idx_logs_thread_id_ts ON logs(thread_id, ts DESC, ts_nanos DESC, id DESC)')
        conn.commit()
    monkeypatch.setattr(term, '_CODEX_METADATA_CACHE', None)
    actual = term._codex_session_metadata_by_tty(
        {'ttys001', '/dev/ttys002', 'ttys003'}, {'/repo'})
    assert actual == expected


def test_new_untitled_projected_thread_still_clears_old_title(tmp_path, monkeypatch):
    from core.routes import term

    monkeypatch.setenv('HOME', str(tmp_path))
    home = tmp_path / '.codex'
    home.mkdir()
    with closing(sqlite3.connect(home / 'state_5.sqlite')) as conn:
        conn.execute('''CREATE TABLE threads (
            id TEXT, title TEXT, name TEXT, preview TEXT, archived INTEGER,
            source TEXT, cwd TEXT, updated_at INTEGER)''')
        conn.executemany('INSERT INTO threads VALUES (?,?,?,?,?,?,?,?)', [
            ('old', 'Previous title', None, 'Previous request', 0, 'cli', '/repo', 10),
            ('new', '   ', None, '', 0, 'cli', '/repo', 20),
        ])
        conn.commit()
    with closing(sqlite3.connect(home / 'logs_2.sqlite')) as conn:
        conn.execute('''CREATE TABLE logs (
            id INTEGER PRIMARY KEY, ts_nanos INTEGER DEFAULT 0,
            process_uuid TEXT, thread_id TEXT, ts INTEGER, target TEXT)''')
        conn.execute('CREATE INDEX idx_logs_thread_id_ts ON logs(thread_id, ts DESC, ts_nanos DESC, id DESC)')
        conn.executemany('INSERT INTO logs (process_uuid,thread_id,ts,target) VALUES (?,?,?,?)', [
            ('pid:123:live', 'old', 10, 'other'),
            ('pid:123:live', 'new', 20, 'codex_core::shell_snapshot'),
            ('pid:123:live', 'older-empty', 20, 'codex_core::shell_snapshot'),
        ])
        conn.execute("UPDATE logs SET ts_nanos = 900 WHERE thread_id = 'new'")
        conn.execute('CREATE INDEX idx_logs_ts ON logs(ts DESC, ts_nanos DESC, id DESC)')
        conn.executemany('INSERT INTO logs (process_uuid,thread_id,ts,target) VALUES (?,?,?,?)',
                         [('pid:999:noise', 'old', 100, 'other')] * 1500)
        conn.commit()
    monkeypatch.setattr(term.subprocess, 'run', lambda *a, **kw:
                        subprocess.CompletedProcess([], 0, stdout='123 ttys001\n'))
    monkeypatch.setattr(term, '_CODEX_METADATA_CACHE', None)
    assert term._codex_session_metadata_by_tty({'ttys001'}, {'/repo'}) == {
        'ttys001': ('new', '', None, []),
    }
