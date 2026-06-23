from __future__ import annotations

import os
import sys
import threading
from pathlib import Path
from typing import Any, Callable

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer
from watchdog.observers.api import BaseObserver
from watchdog.observers.polling import PollingObserver
try:
    from watchdog.observers.kqueue import KqueueObserver
except Exception:  # pragma: no cover - platform/package dependent
    KqueueObserver = None  # type: ignore[assignment]

from core.state import IndexCache


class IndexWatcher:
    """Watch `content/` + `projects/` and rebuild the index on any change, debounced."""

    def __init__(self, root: Path, cache: IndexCache, *,
                 debounce_ms: int,
                 on_rebuild: Callable[[dict[str, Any]], None]) -> None:
        self._root = root
        self._cache = cache
        self._debounce_s = debounce_ms / 1000.0
        self._on_rebuild = on_rebuild
        self._observer: BaseObserver | None = None
        self._handler: FileSystemEventHandler | None = None
        self._timer: threading.Timer | None = None
        self._timer_lock = threading.Lock()
        self._watch_lock = threading.Lock()
        self._watched_dirs: set[str] = set()
        self._stopped = False
        # Legacy index/session/UI state files can still exist under content/.
        # Ignore those writes if an older tool touches them inside the watched
        # tree; current state lives under workspace-local .lab/state/.

    def _is_self_write(self, event: FileSystemEvent) -> bool:
        for attr in ("src_path", "dest_path"):
            p = getattr(event, attr, None)
            if not p:
                continue
            name = Path(p).name
            if name == ".index.json" or name.startswith(".index.json."):
                return True
            # Terminal session metadata writes don't change project or task
            # state, so skip the index rebuild + WS broadcast.
            if name == ".sessions.json" or name.startswith(".sessions.json."):
                return True
            # UI state (tab order, future preferences). Same reasoning.
            if name == ".ui-state.json" or name.startswith(".ui-state.json."):
                return True
        return False

    def _on_change(self, event: FileSystemEvent) -> None:
        if self._is_self_write(event):
            return
        self._refresh_project_watches_for_event(event)
        # Directory-modified events are typically byproducts of child writes we
        # already saw (or of our own atomic index rename). File events give us
        # everything actionable with less noise.
        if getattr(event, "is_directory", False) and event.event_type == "modified":
            return
        with self._timer_lock:
            if self._stopped:
                return
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(self._debounce_s, self._fire)
            self._timer.daemon = True
            self._timer.start()

    def _fire(self) -> None:
        if self._stopped:
            return
        data = self._cache.rebuild()
        try:
            self._on_rebuild(data)
        except Exception:
            # Broadcast failures must not crash the watcher thread.
            pass

    def _polling_observer(self) -> PollingObserver:
        try:
            poll_interval = float(os.environ.get("LAB_WATCHER_POLL_INTERVAL_S", "1.0"))
        except ValueError:
            poll_interval = 1.0
        poll_interval = max(0.05, poll_interval)
        return PollingObserver(timeout=poll_interval)

    def _make_observer(self) -> BaseObserver:
        observer_kind = os.environ.get("LAB_WATCHER_OBSERVER", "").lower()
        if observer_kind == "polling":
            return self._polling_observer()
        if observer_kind == "kqueue" and KqueueObserver is not None:
            return KqueueObserver()  # type: ignore[operator]
        if observer_kind in {"native", "fsevents"}:
            return Observer()
        if sys.platform == "darwin":
            # Watchdog's default macOS FSEvents observer can fail to start on
            # some external volumes. Polling is slower but reliable, and tests
            # can still force a specific observer with LAB_WATCHER_OBSERVER.
            return self._polling_observer()
        return Observer()

    _PROJECT_RECURSIVE_DIRS = {
        ".agents",
        ".claude",
        "docs",
        "notes",
        "notebooks",
        "scripts",
    }

    def _schedule_dir(self, observer: BaseObserver, path: Path, *, recursive: bool) -> None:
        handler = self._handler
        if handler is None:
            return
        try:
            resolved = str(path.resolve())
        except OSError:
            return
        key = f"{resolved}|{int(recursive)}"
        with self._watch_lock:
            if key in self._watched_dirs:
                return
            if not Path(resolved).is_dir():
                return
            observer.schedule(handler, resolved, recursive=recursive)
            self._watched_dirs.add(key)

    def _schedule_project_dir(self, observer: BaseObserver, project_dir: Path) -> None:
        if not project_dir.is_dir():
            return
        # Non-recursive project root catches project.json/tasks.json plus newly
        # created conventional subfolders. Avoid recursive watches here: projects
        # often contain worktrees, assets, or dependency trees that do not affect
        # the lab index and make polling observers expensive on external volumes.
        self._schedule_dir(observer, project_dir, recursive=False)
        for name in self._PROJECT_RECURSIVE_DIRS:
            self._schedule_dir(observer, project_dir / name, recursive=True)

    def _schedule_project_watches(self, observer: BaseObserver) -> None:
        projects = self._root / "projects"
        projects.mkdir(parents=True, exist_ok=True)
        self._schedule_dir(observer, projects, recursive=False)
        for child in projects.iterdir():
            if child.is_dir():
                self._schedule_project_dir(observer, child)

    def _refresh_project_watches_for_event(self, event: FileSystemEvent) -> None:
        observer = self._observer
        if observer is None:
            return
        projects = (self._root / "projects").resolve()
        candidates = []
        for attr in ("src_path", "dest_path"):
            raw = getattr(event, attr, None)
            if raw:
                candidates.append(Path(raw))
        for path in candidates:
            try:
                rel = path.resolve().relative_to(projects)
            except (OSError, ValueError):
                continue
            if not rel.parts:
                continue
            project_dir = projects / rel.parts[0]
            self._schedule_project_dir(observer, project_dir)

    def start(self) -> None:
        handler = FileSystemEventHandler()
        handler.on_any_event = self._on_change
        observer = self._make_observer()
        self._handler = handler
        self._observer = observer
        content = self._root / "content"
        content.mkdir(parents=True, exist_ok=True)
        observer.schedule(handler, str(content), recursive=True)
        self._watched_dirs.add(f"{content.resolve()}|1")
        self._schedule_project_watches(observer)
        observer.start()

    def stop(self) -> None:
        with self._timer_lock:
            self._stopped = True
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=2.0)
            self._observer = None
            self._handler = None
