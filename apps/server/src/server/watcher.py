from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Callable

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from server.state import IndexCache


class IndexWatcher:
    """Watch `content/` and rebuild the index on any change, debounced."""

    def __init__(self, root: Path, cache: IndexCache, *,
                 debounce_ms: int,
                 on_rebuild: Callable[[dict[str, Any]], None]) -> None:
        self._root = root
        self._cache = cache
        self._debounce_s = debounce_ms / 1000.0
        self._on_rebuild = on_rebuild
        self._observer: Observer | None = None
        self._timer: threading.Timer | None = None
        self._timer_lock = threading.Lock()
        self._stopped = False
        # The index cache writes `content/.index.json` on every rebuild via an
        # atomic rename from `.index.json.<tmpsuffix>`. Those writes live inside
        # the watched tree, so we ignore them to avoid an infinite
        # debounce-then-rebuild cascade.

    def _is_self_write(self, event: FileSystemEvent) -> bool:
        for attr in ("src_path", "dest_path"):
            p = getattr(event, attr, None)
            if not p:
                continue
            name = Path(p).name
            if name == ".index.json" or name.startswith(".index.json."):
                return True
            # Terminal sessions metadata lives in content/.sessions.json.
            # Its writes come from /api/term/*; they don't change project or
            # task state, so skip the index rebuild + WS broadcast.
            if name == ".sessions.json" or name.startswith(".sessions.json."):
                return True
            # UI state (tab order, future preferences). Same reasoning.
            if name == ".ui-state.json" or name.startswith(".ui-state.json."):
                return True
        return False

    def _on_change(self, event: FileSystemEvent) -> None:
        if self._is_self_write(event):
            return
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

    def start(self) -> None:
        handler = FileSystemEventHandler()
        handler.on_any_event = self._on_change
        observer = Observer()
        content = self._root / "content"
        content.mkdir(parents=True, exist_ok=True)
        observer.schedule(handler, str(content), recursive=True)
        observer.start()
        self._observer = observer

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
