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


def test_pause_cancels_active_and_queued_scans_preserves_cache_and_resumes(store, monkeypatch):
    monkeypatch.setattr(ws, 'MAX_WORKERS', 1)
    root, vault = Path('/repo'), Path('/vault')
    first = store.read(vault, root, False, lambda _: snapshot('old'))
    release = threading.Event()
    def blocked(progress):
        release.wait(2)
        return snapshot('cancelled')
    try:
        store.read(vault, root, False, blocked, refresh=True)
        store.read(vault, Path('/queued'), False, lambda _: snapshot('queued'))
        assert len(store.resource_status()['scans']) == 2
        store.pause(True)
        assert store.resource_status()['paused']
        assert len(store.resource_status()['scans']) == 1
        cached = store.read(vault, root, False, blocked, refresh=True)
        assert cached.snapshot is first.snapshot and cached.status_code == 200
        assert cached.scan['state'] == 'paused'
        assert store.read(vault, Path('/new'), False, blocked).status_code == 202
        release.set()
        assert store._entries[(str(vault), str(root), False)].done.wait(1)
        assert store.read(vault, root, False, blocked).snapshot is first.snapshot
        assert store.resource_status()['scans'] == []
        store.pause(False)
        updated = store.read(vault, root, False, lambda _: snapshot('new'))
        assert store._entries[(str(vault), str(root), False)].done.wait(1)
        updated = store.read(vault, root, False, lambda _: snapshot('new'))
        assert updated.snapshot.files == [{'path': 'new'}]
    finally:
        release.set()


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
        assert next(iter(store._entries.values())).done.wait(1)
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


def test_capacity_queues_and_starts_without_another_request(store, monkeypatch):
    monkeypatch.setattr(ws, 'MAX_WORKERS', 1)
    monkeypatch.setattr(ws, 'MAX_ROOTS', 2)
    release = threading.Event()
    queued_done = threading.Event()
    calls = []

    def scan(progress):
        calls.append(progress.path)
        release.wait(1)
        if progress.path == '/two':
            queued_done.set()
        return snapshot()

    try:
        store.read(Path('/vault'), Path('/one'), False, scan)
        for _ in range(3):
            result = store.read(Path('/vault'), Path('/two'), False, scan)
            assert result.status_code == 202 and result.scan['state'] == 'queued'
        # Even saturation of the bounded queue is retryable, with no extra job.
        overflow = store.read(Path('/vault'), Path('/three'), False, scan)
        assert overflow.status_code == 202 and len(store._entries) == 2
        assert calls == ['/one'] and len(store._threads) == 1
        release.set()
        assert queued_done.wait(1), 'queued work needed another browser poll to start'
        assert calls == ['/one', '/two']
        result = store.read(Path('/vault'), Path('/three'), False, lambda _: snapshot())
        assert result.status_code == 200
        assert len(store._entries) == 2
    finally:
        release.set()


def test_cold_scans_take_priority_and_cached_refreshes_return_immediately(store, monkeypatch):
    monkeypatch.setattr(ws, 'MAX_WORKERS', 1)
    monkeypatch.setattr(ws, 'REQUEST_WAIT_SECONDS', .5)
    cached = store.read(Path('/vault'), Path('/cached'), False, lambda _: snapshot())
    release = threading.Event()
    calls = []

    def scan(progress):
        calls.append(progress.path)
        release.wait(2)
        return snapshot('updated.md')

    try:
        # Occupy the only worker, then queue a refresh and a first-time listing.
        monkeypatch.setattr(ws, 'REQUEST_WAIT_SECONDS', .001)
        store.read(Path('/vault'), Path('/active'), False, scan)
        monkeypatch.setattr(ws, 'REQUEST_WAIT_SECONDS', .5)
        start = time.monotonic()
        refreshing = store.read(Path('/vault'), Path('/cached'), False, scan, refresh=True)
        assert time.monotonic() - start < .1, 'cached response waited for a scan'
        assert refreshing.snapshot is cached.snapshot and refreshing.status_code == 200
        assert refreshing.scan['state'] == 'refreshing'
        monkeypatch.setattr(ws, 'REQUEST_WAIT_SECONDS', .001)
        queued = store.read(Path('/vault'), Path('/cold'), False, scan)
        assert queued.scan['state'] == 'queued'
        release.set()
        for entry in list(store._entries.values()):
            assert entry.done.wait(1)
        assert calls == ['/active', '/cold', '/cached']
        ready = store.read(Path('/vault'), Path('/cached'), False, scan)
        assert ready.snapshot.files == [{'path': 'updated.md'}]
    finally:
        release.set()


def test_shutdown_discards_queued_jobs(store, monkeypatch):
    monkeypatch.setattr(ws, 'MAX_WORKERS', 1)
    release = threading.Event()
    calls = []

    def scan(progress):
        calls.append(progress.path)
        release.wait(2)
        return snapshot()

    try:
        store.read(Path('/vault'), Path('/active'), False, scan)
        store.read(Path('/vault'), Path('/queued'), False, scan)
        store.close()
        release.set()
        assert calls == ['/active']
        assert not store._entries
    finally:
        release.set()


def test_failure_retains_last_success_and_backs_off(store, monkeypatch):
    store.read(Path('/vault'), Path('/repo'), False, lambda _: snapshot())
    calls = []

    def fail(progress):
        calls.append(1)
        raise OSError(errno.EMFILE, 'too many open files')

    store.read(Path('/vault'), Path('/repo'), False, fail, refresh=True)
    assert next(iter(store._entries.values())).done.wait(1)
    for _ in range(3):
        result = store.read(Path('/vault'), Path('/repo'), False, fail, refresh=True)
        assert result.status_code == 200
        assert result.snapshot.files == [{'path': 'done.md'}]
        assert result.scan['state'] == 'error'
    assert calls == [1]
    for entry in store._entries.values():
        entry.checked -= 61
    store.read(Path('/vault'), Path('/repo'), False, lambda _: snapshot('recovered.md'))
    assert next(iter(store._entries.values())).done.wait(1)
    result = store.read(Path('/vault'), Path('/repo'), False, lambda _: pytest.fail('unexpected rescan'))
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
