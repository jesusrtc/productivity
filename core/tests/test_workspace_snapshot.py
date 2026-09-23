"""Slow, progressing scans survive HTTP deadlines without publishing partials."""
from concurrent.futures import ThreadPoolExecutor
import errno
from pathlib import Path
import threading
import time

import pytest

from core import fsguard, workspace_snapshot as ws


@pytest.fixture
def store(monkeypatch):
    monkeypatch.setattr(ws, 'REQUEST_WAIT_SECONDS', .01)
    store = ws.Store()
    yield store
    store.close()


def snapshot(name='done.md', mtime=1):
    return ws.Snapshot([{'path': name}], mtime, name)


def test_slow_progressing_scan_survives_deadline_and_shares_all_callers(store, monkeypatch):
    monkeypatch.setenv('LAB_FS_TIMEOUT_SECONDS', '0.06')
    release = threading.Event()
    calls = []

    def scan(progress):
        calls.append(1)
        while not release.wait(.005):
            progress.step(Path('/large/note.md'), 'stat')
        return snapshot()

    try:
        with ThreadPoolExecutor(max_workers=8) as clients:
            reads = list(clients.map(lambda _: store.read(Path('/vault'), Path('/large'), False, scan), range(8)))
        assert all(r.status_code == 202 and r.snapshot is None for r in reads)
        time.sleep(.1)  # Total scan exceeds the old guard; individual reads do not stall.
        result = store.read(Path('/vault'), Path('/large'), False, scan)
        assert result.status_code == 202
        assert result.scan['state'] == 'scanning'
        assert result.scan['visited'] > 1
        assert len(calls) == 1
        release.set()
        deadline = time.monotonic() + 1
        while result.snapshot is None and time.monotonic() < deadline:
            result = store.read(Path('/vault'), Path('/large'), False, scan)
        assert result.snapshot.files == [{'path': 'done.md'}]
        assert result.status_code == 200
        assert len(calls) == 1
    finally:
        release.set()


def test_refresh_keeps_complete_snapshot_until_new_scan_finishes(store):
    old = store.read(Path('/vault'), Path('/repo'), False, lambda _: snapshot())
    release = threading.Event()

    def scan(progress):
        progress.step(Path('/repo/new.md'), 'stat')
        release.wait(1)
        return snapshot('new.md', 2)

    try:
        updating = store.read(Path('/vault'), Path('/repo'), False, scan, refresh=True)
        assert updating.status_code == 200
        assert updating.scan['state'] == 'refreshing'
        assert updating.snapshot is old.snapshot
        release.set()
        ready = store.read(Path('/vault'), Path('/repo'), False, scan)
        assert ready.scan['state'] == 'ready'
        assert ready.snapshot.files == [{'path': 'new.md'}]
    finally:
        release.set()


def test_stall_reports_exact_path_once_without_spawning_replacements(store, monkeypatch, caplog):
    monkeypatch.setenv('LAB_FS_TIMEOUT_SECONDS', '0.02')
    release = threading.Event()
    calls = []

    def scan(progress):
        calls.append(1)
        progress.step(Path('/repo/mounted/docs'), 'scandir')
        release.wait(1)
        return snapshot()

    try:
        store.read(Path('/vault'), Path('/repo'), False, scan)
        time.sleep(.025)
        for _ in range(3):
            result = store.read(Path('/vault'), Path('/repo'), False, scan, refresh=True)
            assert result.status_code == 503
            assert result.scan['state'] == 'stalled'
            assert result.scan['path'] == '/repo/mounted/docs'
            assert result.scan['operation'] == 'scandir'
        assert len(calls) == 1
        assert caplog.text.count('workspace scan stalled') == 1
        # A stalled full-tree scan does not take a slot from small guarded reads.
        assert fsguard.guarded(Path('/vault'), lambda: 42) == 42
        release.set()
        result = store.read(Path('/vault'), Path('/repo'), False, scan)
        assert result.status_code == 200
    finally:
        release.set()


def test_capacity_is_bounded_without_queue_and_cache_is_evicted(store, monkeypatch):
    monkeypatch.setattr(ws, 'MAX_WORKERS', 1)
    monkeypatch.setattr(ws, 'MAX_ROOTS', 2)
    release = threading.Event()
    calls = []

    def scan(progress):
        calls.append(progress.path)
        release.wait(1)
        return snapshot()

    try:
        store.read(Path('/vault'), Path('/one'), False, scan)
        result = store.read(Path('/vault'), Path('/two'), False, scan)
        assert result.status_code == 503 and result.scan['state'] == 'busy'
        assert calls == ['/one']
        release.set()
        store.read(Path('/vault'), Path('/one'), False, scan)
        result = store.read(Path('/vault'), Path('/three'), False, lambda _: snapshot())
        assert result.status_code == 200
        assert len(store._entries) == 2
    finally:
        release.set()


def test_failure_retains_last_success_and_backs_off(store, monkeypatch):
    store.read(Path('/vault'), Path('/repo'), False, lambda _: snapshot())
    calls = []

    def fail(progress):
        calls.append(1)
        raise OSError(errno.EMFILE, 'too many open files')

    for _ in range(3):
        result = store.read(Path('/vault'), Path('/repo'), False, fail, refresh=True)
        assert result.status_code == 200
        assert result.snapshot.files == [{'path': 'done.md'}]
        assert result.scan['state'] == 'error'
    assert calls == [1]
    for entry in store._entries.values():
        entry.checked -= 61
    result = store.read(Path('/vault'), Path('/repo'), False, lambda _: snapshot('recovered.md'))
    assert result.snapshot.revision == 'recovered.md'


def test_root_vault_and_dotfile_settings_are_separate(store):
    for vault, root, hidden, name in [('/one', '/repo', False, 'visible'),
                                     ('/one', '/repo', True, 'hidden'),
                                     ('/two', '/repo', False, 'other-vault'),
                                     ('/one', '/other', False, 'other-root')]:
        result = store.read(Path(vault), Path(root), hidden, lambda _, name=name: snapshot(name))
        assert result.snapshot.revision == name
    result = store.read(Path('/one'), Path('/repo'), False, lambda _: pytest.fail('unexpected rescan'))
    assert result.snapshot.revision == 'visible'


def test_shutdown_cancels_walk_between_syscalls(store):
    started = threading.Event()
    exited = threading.Event()

    def scan(progress):
        started.set()
        try:
            while True:
                progress.step(Path('/repo'), 'scandir')
                time.sleep(.001)
        finally:
            exited.set()

    store.read(Path('/vault'), Path('/repo'), False, scan)
    assert started.is_set()
    store.close()
    assert exited.wait(.1)
    assert not store._threads
    assert not store._entries
