import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from core.sidebar_cache import Store


def test_disk_survives_restart_and_stale_reads_do_not_wait(tmp_path):
    store = Store()
    assert store.read(tmp_path, ('repo',), lambda: {'files': ['a']}, wait=2).value == {'files': ['a']}
    store.close()
    store = Store()
    gate = threading.Event()
    calls = []

    def collect():
        calls.append(1)
        gate.wait(2)
        return {'files': ['b']}

    try:
        start = time.monotonic()
        with ThreadPoolExecutor(max_workers=8) as pool:
            reads = list(pool.map(lambda _: store.read(tmp_path, ('repo',), collect, ttl=0), range(8)))
        assert time.monotonic() - start < .5
        assert all(row.value == {'files': ['a']} and row.pending for row in reads)
        assert len(calls) == 1
        gate.set()
        deadline = time.monotonic() + 2
        while store.read(tmp_path, ('repo',), collect).pending:
            assert time.monotonic() < deadline
            time.sleep(.01)
        assert store.read(tmp_path, ('repo',), collect).value == {'files': ['b']}
    finally:
        gate.set()
        store.close()


def test_failed_refresh_retains_last_good_result_and_backs_off(tmp_path):
    store = Store()
    try:
        store.read(tmp_path, ('repo',), lambda: {'files': ['a']}, wait=2)
        calls = []
        def fail():
            calls.append(1)
            raise RuntimeError('Git failed')
        store.read(tmp_path, ('repo',), fail, ttl=0)
        deadline = time.monotonic() + 2
        while (result := store.read(tmp_path, ('repo',), fail, ttl=0)).pending:
            assert time.monotonic() < deadline
            time.sleep(.01)
        assert result.value == {'files': ['a']}
        assert result.error == 'Git failed'
        assert len(calls) == 1
    finally:
        store.close()


def test_eviction_and_vault_isolation(tmp_path, monkeypatch):
    from core import sidebar_cache
    monkeypatch.setattr(sidebar_cache, 'MAX_ENTRIES', 2)
    store = Store()
    try:
        for i in range(4):
            assert store.read(tmp_path, (i,), lambda i=i: {'i': i}, wait=2).value == {'i': i}
        with sqlite3.connect(tmp_path / '.lab/cache/sidebar-v1.sqlite3') as db:
            assert db.execute('SELECT count(*) FROM snapshots').fetchone()[0] == 2
        assert store.read(tmp_path / 'other', (3,), lambda: {'other': True}, wait=2).value == {'other': True}
    finally:
        store.close()


def test_same_checkout_serializes_git_without_blocking_directory_reads(tmp_path):
    store = Store()
    gate = threading.Event()
    entered = threading.Event()
    try:
        store.read(tmp_path, ('first',), lambda: gate.wait(2) or {}, wait=0, group='repo')
        store.read(tmp_path, ('second',), lambda: entered.set() or {}, wait=0, group='repo')
        other = store.read(tmp_path, ('directory',), lambda: {'entries': []}, wait=1)
        assert other.value == {'entries': []}
        assert not entered.is_set()
        gate.set()
        assert entered.wait(2)
    finally:
        gate.set()
        store.close()


def test_corrupt_sqlite_still_serves_a_bounded_live_result(tmp_path):
    cache = tmp_path / '.lab/cache'
    cache.mkdir(parents=True)
    (cache / 'sidebar-v1.sqlite3').write_bytes(b'not a database')
    store = Store()
    try:
        result = store.read(tmp_path, ('repo',), lambda: {'files': ['a']}, wait=2)
        assert result.value == {'files': ['a']}
        assert not result.error
        assert store.read(tmp_path, ('repo',), lambda: 1 / 0).value == result.value
        assert sum(len(row[1]) for row in store._fallback.values()) < 2 * 1024 * 1024
    finally:
        store.close()


def test_recent_pages_sort_filter_and_do_not_return_the_entire_snapshot(tmp_path):
    store = Store()
    entries = [{'path':f'src/{i}.py', 'git_tracked':True, '_extension':'py',
                '_rank_updated':499-i, '_rank_name':i, '_rank_type':i} for i in range(500)]
    entries.append({'path':'.hidden.py','_extension':'py','_rank_updated':-1})
    try:
        first = store.read(tmp_path, ('recent',), lambda: {'entries':entries,'mode':'mtime'}, wait=2,
                           page=(0,'updated',False,('py',))).value
        assert first['total'] == 500
        assert first['files'][0] == 'src/499.py'
        assert len(first['entries']) == 200
        assert first['next_offset'] == 200
        second = store.read(tmp_path, ('recent',), lambda: 1/0, page=(200,'updated',False,('py',))).value
        assert not set(first['files']) & set(second['files'])
        assert second['files'][0] == 'src/299.py'
        assert store.read(tmp_path, ('recent',), lambda:1/0, page=(0,'name',False,('md',))).value['total'] == 0
    finally:
        store.close()
