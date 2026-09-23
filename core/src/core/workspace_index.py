"""Native change notifications and reusable directory metadata for Files.

No per-file descriptors (not kqueue), no polling observer walking repositories,
no filesystem work on HTTP/event-dispatch threads. A periodic reconciliation in
workspace_snapshot covers unavailable observers and dropped notifications.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
import sys
import threading
import time

from watchdog.events import FileSystemEventHandler

from core.workspace_scan import SKIP_DIRS

log = logging.getLogger(__name__)
MAX_WATCHES = 32
MAX_DIRTY_PATHS = 4096


def _native_observer():
    if os.environ.get('LAB_WORKSPACE_WATCHER') == 'off':
        return None
    if sys.platform == 'darwin':
        from watchdog.observers.fsevents import FSEventsObserver
        return FSEventsObserver()
    if sys.platform.startswith('linux'):
        from watchdog.observers.inotify import InotifyObserver
        return InotifyObserver()
    if sys.platform == 'win32':
        from watchdog.observers.read_directory_changes import WindowsApiObserver
        return WindowsApiObserver()
    return None


class ChangeHub:
    """Share native watches across roots, dotfile views, and linked aliases."""
    def __init__(self):
        self._lock = threading.Lock()
        self._observer = None
        self._started = False
        self._watches = {}  # physical path -> (watch, set of DirectoryIndex)
        self._health = {}

    def _publish_health(self):
        emitters = {emitter.watch: emitter for emitter in self._observer.emitters}
        health = {}
        for watch, members in self._watches.values():
            for member in members:
                health.setdefault(member, []).append(emitters.get(watch))
        self._health = health

    def add(self, index, path: Path) -> bool:
        with self._lock:
            try:
                if not self._started:
                    self._started = True
                    self._observer = _native_observer()
                    if self._observer:
                        self._observer.start()
                observer = self._observer
                if observer is None:
                    return False
                covering = next((p for p in self._watches if path.is_relative_to(p)), None)
                if covering is not None:
                    watch, members = self._watches[covering]
                    if self._alive(watch):
                        if index not in members:
                            observer.add_handler_for_watch(index, watch)
                            members.add(index)
                            self._publish_health()
                        return True
                    observer.unschedule(watch)
                    del self._watches[covering]
                    self._publish_health()
                if len(self._watches) >= MAX_WATCHES:
                    return False
                watch = observer.schedule(index, str(path), recursive=True)
                self._watches[path] = (watch, {index})
                self._publish_health()
                return self._alive(watch)
            except (OSError, RuntimeError, ImportError) as exc:
                log.warning('workspace native watch unavailable path=%s: %s', path, exc)
                return False

    def _alive(self, watch) -> bool:
        return any(emitter.watch == watch and emitter.is_alive() for emitter in self._observer.emitters)

    def healthy(self, index) -> bool:
        # HTTP reads must not wait on schedule()/unschedule() doing OS work.
        emitters = self._health.get(index, ())
        return bool(emitters) and all(emitter and emitter.is_alive() for emitter in emitters)

    def remove(self, index, *, keep=()) -> None:
        with self._lock:
            for path, (watch, members) in list(self._watches.items()):
                if index not in members:
                    continue
                if any(target.is_relative_to(path) for target in keep):
                    continue
                members.remove(index)
                self._observer.remove_handler_for_watch(index, watch)
                if not members:
                    self._observer.unschedule(watch)
                    del self._watches[path]
            if self._observer:
                self._publish_health()

    def close(self) -> None:
        with self._lock:
            observer, self._observer = self._observer, None
            self._watches.clear()
            self._health = {}
        if observer:
            observer.stop()
            observer.join(timeout=.5)


class DirectoryIndex(FileSystemEventHandler):
    def __init__(self, root: Path, hidden: bool, hub: ChangeHub):
        self.root = root
        self.hidden = hidden
        self.hub = hub
        self._lock = threading.Lock()
        self._dirs = {}
        self._canonical = {}
        self._aliases = {}  # physical path -> logical paths, including internal links
        self._dirty = set()
        self._subtrees = set()
        self._full = True
        self._changed = time.monotonic()
        self._first_changed = self._changed
        self._watch_complete = False
        self._closed = False

    def pending(self) -> tuple[bool, float, float]:
        with self._lock:
            return bool(self._full or self._dirty or self._subtrees), self._changed, self._first_changed

    def watching(self) -> bool:
        return self._watch_complete and self.hub.healthy(self)

    def invalidate(self) -> None:
        with self._lock:
            self._mark(None)

    def _mark(self, path: Path | None, subtree=False):
        now = time.monotonic()
        if not (self._full or self._dirty or self._subtrees):
            self._first_changed = now
        self._changed = now
        if path is None or len(self._dirty) + len(self._subtrees) >= MAX_DIRTY_PATHS:
            self._full = True
            self._dirty.clear()
            self._subtrees.clear()
        else:
            self._dirty.add(path)
            if subtree:
                self._subtrees.add(path)

    def on_any_event(self, event):
        if event.event_type not in {'created', 'modified', 'deleted', 'moved', 'closed'}:
            return  # Reads/open/close-without-write must never dirty the cache.
        with self._lock:
            if self._closed:
                return
            for raw in (event.src_path, getattr(event, 'dest_path', '')):
                if not raw:
                    continue
                actual = Path(os.fsdecode(raw))
                for physical, logical_paths in self._aliases.items():
                    if not actual.is_relative_to(physical):
                        continue
                    suffix = actual.relative_to(physical)
                    for logical in logical_paths:
                        path = logical / suffix
                        rel = path.relative_to(self.root)
                        # Git changes can alter worktree "recent" flags without
                        # touching visible file mtimes. Rebuild rows from cached
                        # metadata, rather than enumerating .git.
                        if '.git' in rel.parts:
                            self._mark(path.parent)
                            continue
                        if any(part in SKIP_DIRS or (part.startswith('.') and not self.hidden) for part in rel.parts):
                            continue
                        self._mark(path.parent)
                        # A file event can replace/retarget a symlink. Drop its
                        # cached descendants too, even if its parent survived.
                        self._mark(path, subtree=not event.is_directory or event.event_type in {'created', 'deleted', 'moved'})

    def begin(self, progress, *, full=False):
        # Starting subscriptions before the first walk closes the read/watch
        # race. Notifications arriving during collection remain pending.
        progress.step(self.root, 'watch root')
        physical = self.root.resolve()
        with self._lock:
            self._aliases.setdefault(physical, set()).add(self.root)
        root_exists = physical.is_dir()
        self._watch_complete = root_exists and self.hub.add(self, physical)
        with self._lock:
            view = View(self, self._dirs.copy(), self._canonical.copy(),
                        self._dirty.copy(), self._subtrees.copy(), full or self._full)
            self._dirty.clear()
            self._subtrees.clear()
            self._full = False
        view.aliases[physical] = {self.root}
        view.targets.add(physical)
        return view

    def close(self):
        with self._lock:
            self._closed = True
        self.hub.remove(self)


class View:
    """One transactional walk; a failed scan cannot poison cached metadata."""
    def __init__(self, index, dirs, canonical, dirty, subtrees, full):
        self.index, self.dirs, self.canonical_paths = index, dirs, canonical
        self.dirty, self.subtrees, self.full = dirty, subtrees, full
        self.used = set()
        self.aliases = {}
        self.targets = set()
        self.watch_complete = index._watch_complete
        if full:
            self.dirs.clear()
            self.canonical_paths.clear()
        else:
            for path in list(self.canonical_paths):
                if path.parent in dirty or self._invalidated(path):
                    del self.canonical_paths[path]

    def _invalidated(self, path):
        # Walk ancestors instead of comparing against every changed file in a
        # checkout burst (which would make a cached traversal quadratic).
        return bool(self.subtrees) and (path in self.subtrees or any(parent in self.subtrees for parent in path.parents))

    def listing(self, path, loader):
        self.used.add(path)
        if path not in self.dirs or path in self.dirty or self._invalidated(path):
            self.dirs[path] = loader()
        return self.dirs[path]

    def canonical(self, path: Path, progress) -> Path:
        if path not in self.canonical_paths:
            progress(path, 'resolve path')
            self.canonical_paths[path] = path.resolve()
        return self.canonical_paths[path]

    def link(self, path: Path, is_dir: bool, progress):
        physical = self.canonical(path, progress)
        self.aliases.setdefault(physical, set()).add(path)
        with self.index._lock:
            self.index._aliases.setdefault(physical, set()).add(path)
        target = physical if is_dir else physical.parent
        self.targets.add(target)
        progress(target, 'watch linked target')
        self.watch_complete = self.index.hub.add(self.index, target) and self.watch_complete

    def commit(self):
        # Removed links must release subscriptions in a long-lived workspace.
        self.index.hub.remove(self.index, keep=self.targets)
        with self.index._lock:
            self.index._dirs = {path: listing for path, listing in self.dirs.items() if path in self.used}
            self.index._canonical = self.canonical_paths
            self.index._aliases = self.aliases
            self.index._watch_complete = self.watch_complete

    def abort(self):
        # Recover all invalidations consumed by this attempt, including a
        # periodic full reconciliation. Concurrent events are preserved too.
        with self.index._lock:
            if self.full:
                self.index._full = True
            self.index._dirty.update(self.dirty)
            self.index._subtrees.update(self.subtrees)
