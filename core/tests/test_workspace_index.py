"""Directory invalidation must detect edits without rewalking unchanged trees."""
from pathlib import Path
import os
import time

import pytest
from watchdog.events import FileModifiedEvent, FileCreatedEvent, FileDeletedEvent, DirMovedEvent

from core import workspace_index as wi, workspace_snapshot as ws, workspace_scan


class Hub:
    def add(self, *_):
        return True

    def healthy(self, *_):
        return True

    def remove(self, *_, **kwargs):
        pass


def collect(index, *, full=False, during=None):
    progress = ws.Progress(str(index.root))
    view = index.begin(progress, full=full)
    try:
        rows = {str(row.path.relative_to(index.root)): row.stat.st_mtime_ns
                for row in workspace_scan.walk(index.root, cache=view) if row.is_file}
        if during:
            during()
        view.commit()
        return rows
    except Exception:
        view.abort()
        raise


def test_events_refresh_only_changed_directories_and_preserve_inplace_edits(tmp_path, monkeypatch):
    for name in ('one', 'two'):
        (tmp_path / name).mkdir()
        (tmp_path / name / 'file.py').write_text('first')
    index = wi.DirectoryIndex(tmp_path, False, Hub())
    original = collect(index)
    scanned = []
    scandir = os.scandir

    def counted(path):
        scanned.append(Path(path))
        return scandir(path)

    monkeypatch.setattr(os, 'scandir', counted)
    parent_mtime = (tmp_path / 'one').stat().st_mtime_ns
    target = tmp_path / 'one/file.py'
    os.utime(target, ns=(original['one/file.py'] + 1000000000,) * 2)
    assert (tmp_path / 'one').stat().st_mtime_ns == parent_mtime
    index.on_any_event(FileModifiedEvent(str(target)))
    updated = collect(index)
    assert updated['one/file.py'] != original['one/file.py']
    assert updated['two/file.py'] == original['two/file.py']
    assert scanned == [tmp_path / 'one']
    scanned.clear()
    assert collect(index) == updated
    assert scanned == []


def test_create_delete_move_and_events_during_collection(tmp_path):
    (tmp_path / 'before').mkdir()
    (tmp_path / 'before/a.py').write_text('a')
    index = wi.DirectoryIndex(tmp_path, False, Hub())
    collect(index)
    (tmp_path / 'before').rename(tmp_path / 'after')
    index.on_any_event(DirMovedEvent(str(tmp_path / 'before'), str(tmp_path / 'after')))
    assert set(collect(index)) == {'after/a.py'}
    target = tmp_path / 'after/b.py'
    target.write_text('b')
    collect(index, during=lambda: index.on_any_event(FileCreatedEvent(str(target))))
    assert index.pending()[0]
    assert set(collect(index)) == {'after/a.py', 'after/b.py'}
    target.unlink()
    index.on_any_event(FileDeletedEvent(str(target)))
    assert set(collect(index)) == {'after/a.py'}
    assert not index.pending()[0]


def test_link_targets_and_retargeting_invalidate_cached_descendants(tmp_path):
    root = tmp_path / 'root'
    root.mkdir()
    for name in ('a', 'b'):
        folder = tmp_path / name
        folder.mkdir()
        (folder / f'{name}.py').write_text(name)
    link = root / 'linked'
    link.symlink_to(tmp_path / 'a', target_is_directory=True)
    index = wi.DirectoryIndex(root, False, Hub())
    first = collect(index)
    target = tmp_path / 'a/a.py'
    os.utime(target, ns=(first['linked/a.py'] + 1000000000,) * 2)
    index.on_any_event(FileModifiedEvent(str(target)))
    assert collect(index)['linked/a.py'] != first['linked/a.py']
    link.unlink()
    link.symlink_to(tmp_path / 'b', target_is_directory=True)
    index.on_any_event(FileModifiedEvent(str(link)))
    assert set(collect(index)) == {'linked/b.py'}
    assert tmp_path / 'a' not in index._aliases


def test_overflow_and_failed_collection_keep_reconciliation_pending(tmp_path, monkeypatch):
    index = wi.DirectoryIndex(tmp_path, False, Hub())
    collect(index)
    monkeypatch.setattr(wi, 'MAX_DIRTY_PATHS', 2)
    for i in range(4):
        index.on_any_event(FileModifiedEvent(str(tmp_path / f'{i}.py')))
    assert index._full
    with pytest.raises(OSError):
        collect(index, during=lambda: (_ for _ in ()).throw(OSError('unavailable')))
    assert index._full
    collect(index)
    assert not index.pending()[0]


def test_store_idle_reads_do_not_scan_and_native_failure_uses_periodic_fallback(tmp_path, monkeypatch):
    monkeypatch.setenv('LAB_WORKSPACE_WATCHER', 'off')
    monkeypatch.setattr(ws, 'REQUEST_WAIT_SECONDS', .5)
    store = ws.Store()
    calls = []

    def scan(progress):
        calls.append(1)
        return ws.Snapshot([], None, str(len(calls)))

    try:
        store.read(tmp_path, tmp_path, False, scan)
        entry = next(iter(store._entries.values()))
        entry.reconciled -= 5  # Old code scanned every two seconds.
        for _ in range(10):
            assert store.read(tmp_path, tmp_path, False, scan).scan['state'] == 'ready'
        assert len(calls) == 1
        entry.reconciled -= ws.FALLBACK_SECONDS
        store.read(tmp_path, tmp_path, False, scan)
        assert entry.done.wait(1)
        assert len(calls) == 2
        store.read(tmp_path, tmp_path, False, scan, refresh=True)
        assert entry.done.wait(1)
        assert store.read(tmp_path, tmp_path, False, scan).snapshot.revision == '3'
    finally:
        store.close()


def test_native_watcher_detects_edit_and_releases_subscriptions(tmp_path, monkeypatch):
    monkeypatch.delenv('LAB_WORKSPACE_WATCHER', raising=False)
    target = tmp_path / 'file.py'
    target.write_text('original')
    hub = wi.ChangeHub()
    # macOS reports canonical /private paths through FSEvents.
    index = wi.DirectoryIndex(tmp_path, False, hub)
    try:
        original = collect(index)
        if not index.watching():
            pytest.skip('native filesystem notifications unavailable')
        # Allow subscription startup/history delivery before exercising an edit.
        time.sleep(.2)
        collect(index)
        target.write_text('updated')
        deadline = time.monotonic() + 5
        while not index.pending()[0] and time.monotonic() < deadline:
            time.sleep(.02)
        assert index.pending()[0]
        assert collect(index)['file.py'] != original['file.py']
        index.close()
        assert not hub._watches
        assert not hub.healthy(index)
    finally:
        hub.close()


def test_native_watches_are_shared_bounded_and_pruned(tmp_path, monkeypatch):
    class Emitter:
        def __init__(self, watch):
            self.watch = watch

        def is_alive(self):
            return True

    class Observer:
        def __init__(self):
            self.emitters = set()

        def start(self):
            pass

        def schedule(self, handler, path, recursive):
            emitter = Emitter(path)
            self.emitters.add(emitter)
            return emitter.watch

        def add_handler_for_watch(self, *args):
            pass

        def remove_handler_for_watch(self, *args):
            pass

        def unschedule(self, watch):
            self.emitters = {e for e in self.emitters if e.watch != watch}

        def stop(self):
            self.emitters.clear()

        def join(self, **kwargs):
            pass

    monkeypatch.setattr(wi, '_native_observer', Observer)
    monkeypatch.setattr(wi, 'MAX_WATCHES', 2)
    hub = wi.ChangeHub()
    first, second = object(), object()
    try:
        assert hub.add(first, tmp_path / 'repo')
        assert hub.add(second, tmp_path / 'repo/subfolder')
        assert len(hub._watches) == 1
        assert hub.add(first, tmp_path / 'linked')
        assert not hub.add(first, tmp_path / 'over-capacity')
        hub.remove(first, keep=[tmp_path / 'repo'])
        assert len(hub._watches) == 1
        assert hub.add(second, tmp_path / 'replacement')
        hub.remove(first)
        assert hub.healthy(second)
        hub.remove(second)
        assert not hub._watches and not hub._health
    finally:
        hub.close()
