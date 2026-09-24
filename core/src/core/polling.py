"""Polling snapshots with less per-entry bookkeeping and unchanged events."""
from __future__ import annotations

import errno
import os
from stat import S_ISDIR

from watchdog.observers.api import BaseObserver
from watchdog.observers.polling import PollingEmitter, PollingObserver
from watchdog.utils.dirsnapshot import DirectorySnapshot


class _PollingSnapshot(DirectorySnapshot):
    @property
    def paths(self):
        # Snapshots are complete before comparison and never edited afterward.
        # Dict key views support the same set operations used by watchdog's
        # unmodified diff, without rebuilding eight full sets per comparison.
        return self._stat_info.keys()

    def walk(self, root):
        if self.stat is not os.stat or self.listdir is not os.scandir:
            # Preserve the upstream behavior for custom filesystem adapters.
            yield from super().walk(root)
            return
        try:
            entries = list(self.listdir(root))
        except OSError as error:
            if error.errno in (errno.ENOENT, errno.ENOTDIR, errno.EINVAL):
                return
            raise
        directories = []
        for entry in entries:
            try:
                # These are fresh DirEntry objects; no prior stat is cached.
                # Follow links exactly as the original os.stat call does.
                info = entry.stat()
            except OSError:
                continue
            yield entry.path, info
            if self.recursive and S_ISDIR(info.st_mode):
                directories.append(entry.path)
        for path in directories:
            try:
                yield from self.walk(path)
            except PermissionError:
                pass


class _PollingEmitter(PollingEmitter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._take_snapshot = lambda: _PollingSnapshot(
            self.watch.path, recursive=self.watch.is_recursive,
            stat=kwargs.get('stat', os.stat), listdir=kwargs.get('listdir', os.scandir),
        )


class SnapshotPollingObserver(PollingObserver):
    def __init__(self, *, timeout=1.0):
        # Same observer/emitter lifecycle, polling wait, diff and event queue.
        # Only the snapshot factory differs from the standard PollingObserver.
        BaseObserver.__init__(self, _PollingEmitter, timeout=timeout)
