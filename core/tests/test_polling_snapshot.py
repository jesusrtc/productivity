"""Optimized polling must report the same complete filesystem changes."""
import errno
import os
from pathlib import Path

import pytest
from watchdog.observers.api import EventQueue, ObservedWatch
from watchdog.utils.dirsnapshot import DirectorySnapshot, DirectorySnapshotDiff, EmptyDirectorySnapshot

from core.polling import _PollingEmitter, _PollingSnapshot


def _events(before, after):
    diff = DirectorySnapshotDiff(before, after)
    return {f'{kind}_{change}': set(getattr(diff, f'{kind}_{change}'))
            for kind in ('files', 'dirs') for change in ('created', 'deleted', 'modified', 'moved')}


def _pair(root, recursive=True):
    before = DirectorySnapshot(str(root), recursive=recursive)
    candidate = _PollingSnapshot(str(root), recursive=recursive)
    assert candidate.paths == before.paths
    for path in before.paths:
        assert candidate.inode(path) == before.inode(path)
        assert candidate.path(before.inode(path)) == before.path(before.inode(path))
        assert candidate.isdir(path) == before.isdir(path)
        assert candidate.mtime(path) == before.mtime(path)
        assert candidate.size(path) == before.size(path)
    return before, candidate


@pytest.mark.parametrize('recursive', [False, True])
def test_snapshots_and_changes_match_for_files_directories_links_and_atomic_replacement(tmp_path, recursive):
    (tmp_path / 'nested').mkdir()
    (tmp_path / 'nested' / 'inside.txt').write_text('inside')
    (tmp_path / 'source.txt').write_text('original')
    (tmp_path / 'removed.txt').write_text('remove')
    (tmp_path / 'renamed.txt').write_text('move')
    (tmp_path / 'link.txt').symlink_to('source.txt')
    (tmp_path / 'directory-link').symlink_to('nested', target_is_directory=True)
    (tmp_path / 'dangling').symlink_to('missing')
    os.link(tmp_path / 'source.txt', tmp_path / 'hard-link.txt')
    old, candidate_old = _pair(tmp_path, recursive)
    assert _events(EmptyDirectorySnapshot(), old) == _events(EmptyDirectorySnapshot(), candidate_old)
    # Every mutation is compared using both implementations; no synthetic
    # snapshot bypasses actual inode, link target, mtime or size behavior.
    actions = [
        lambda: (tmp_path / 'source.txt').write_text('changed and longer'),
        lambda: (tmp_path / 'removed.txt').unlink(),
        lambda: (tmp_path / 'renamed.txt').rename(tmp_path / 'new-name.txt'),
        lambda: (tmp_path / 'created.txt').write_text('created'),
        lambda: (tmp_path / 'nested').rename(tmp_path / 'moved-directory'),
        lambda: (tmp_path / 'replacement.txt').write_text('atomic replacement'),
        lambda: (tmp_path / 'replacement.txt').replace(tmp_path / 'source.txt'),
        lambda: (tmp_path / 'missing').write_text('link target appears'),
    ]
    for mutate in actions:
        mutate()
        new, candidate_new = _pair(tmp_path, recursive)
        assert _events(old, new) == _events(candidate_old, candidate_new)
        old, candidate_old = new, candidate_new
    assert _events(old, EmptyDirectorySnapshot()) == _events(candidate_old, EmptyDirectorySnapshot())


def test_custom_stat_and_listing_keep_upstream_semantics(tmp_path):
    file = tmp_path / 'entry.txt'
    file.write_text('entry')
    calls = []
    def stat(path):
        calls.append(str(path))
        if str(path) == str(file):
            raise PermissionError('unreadable entry')
        return os.stat(path)
    snapshots = [kind(str(tmp_path), stat=stat) for kind in (DirectorySnapshot, _PollingSnapshot)]
    assert snapshots[0].paths == snapshots[1].paths == {str(tmp_path)}
    assert calls == [str(tmp_path), str(file)] * 2
    for error in (errno.ENOENT, errno.ENOTDIR, errno.EINVAL, errno.EACCES):
        def listing(_root):
            raise OSError(error, 'listing failed')
        if error == errno.EACCES:
            for kind in (DirectorySnapshot, _PollingSnapshot):
                with pytest.raises(OSError):
                    kind(str(tmp_path), listdir=listing)
        else:
            assert DirectorySnapshot(str(tmp_path), listdir=listing).paths == _PollingSnapshot(str(tmp_path), listdir=listing).paths


def test_native_entries_do_not_hide_deletion_between_enumeration_and_stat(tmp_path, monkeypatch):
    actual_scandir = os.scandir
    file = tmp_path / 'disappearing.txt'
    def listing(root):
        with actual_scandir(root) as iterator:
            entries = list(iterator)
        file.unlink()
        return iter(entries)
    # Make this the native listing hook for the candidate's fast path. Its
    # entries still come from the OS and have never had stat() called on them.
    monkeypatch.setattr(os, 'scandir', listing)
    for kind in (DirectorySnapshot, _PollingSnapshot):
        file.write_text('will disappear')
        snapshot = kind(str(tmp_path), listdir=listing)
        assert snapshot.paths == {str(tmp_path)}


def test_native_byte_paths_and_unicode_names_keep_snapshot_identity(tmp_path):
    (tmp_path / 'café folder').mkdir()
    (tmp_path / 'café folder' / 'a b.txt').write_text('value')
    root = os.fsencode(tmp_path)
    baseline, candidate = DirectorySnapshot(root), _PollingSnapshot(root)
    assert candidate.paths == baseline.paths
    assert all(candidate.stat_info(path) == baseline.stat_info(path) for path in baseline.paths)
    assert _events(baseline, baseline) == _events(candidate, candidate)


def test_polling_emitter_keeps_normal_diff_and_event_delivery(tmp_path):
    queue = EventQueue()
    emitter = _PollingEmitter(queue, ObservedWatch(str(tmp_path), recursive=True), timeout=.05)
    emitter.on_thread_start()
    assert isinstance(emitter._snapshot, _PollingSnapshot)
    file = tmp_path / 'created.txt'
    file.write_text('first')
    emitter.queue_events(0)
    events = []
    while not queue.empty():
        events.append(queue.get_nowait()[0])
    assert any(event.event_type == 'created' and event.src_path == str(file) and not event.is_directory for event in events)
    file.write_text('second, longer')
    emitter.queue_events(0)
    events = []
    while not queue.empty():
        events.append(queue.get_nowait()[0])
    assert any(event.event_type == 'modified' and event.src_path == str(file) for event in events)
    emitter.stop()
