"""Bounded background snapshots for the Files view and its refresh poll.

A large tree is not a failed filesystem read. HTTP callers wait only briefly;
the same scan keeps progressing until a complete snapshot can be published.
These workers are separate from fsguard so indexing cannot starve small reads.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
import logging
from pathlib import Path
import threading
import time
from typing import Callable

from core import fsguard
from core.workspace_index import ChangeHub, DirectoryIndex


log = logging.getLogger(__name__)
REQUEST_WAIT_SECONDS = 0.15
RECONCILE_SECONDS = 300.0
FALLBACK_SECONDS = 30.0
DEBOUNCE_SECONDS = 0.2
MAX_DEBOUNCE_SECONDS = 1.0
MAX_WORKERS = 2
MAX_ROOTS = 32


class ScanCancelled(Exception):
    pass


@dataclass
class Progress:
    path: str
    operation: str = "starting"
    visited: int = 0
    started: float = field(default_factory=time.monotonic)
    last_step: float = field(default_factory=time.monotonic)
    cancelled: threading.Event = field(default_factory=threading.Event)
    warned: bool = False
    cache: object = None

    def step(self, path: Path, operation: str) -> None:
        if self.cancelled.is_set():
            raise ScanCancelled()
        self.path, self.operation = str(path), operation
        self.last_step = time.monotonic()
        if operation == "stat":
            self.visited += 1

    def status(self, state: str) -> dict:
        now = time.monotonic()
        return {"state": state, "path": self.path, "operation": self.operation,
                "visited": self.visited, "elapsed_seconds": round(now - self.started, 2),
                "idle_seconds": round(now - self.last_step, 2)}


@dataclass
class Snapshot:
    files: list[dict]
    mtime: float | None
    revision: str
    notebooks: dict[str, str] = field(default_factory=dict)


@dataclass
class _Entry:
    snapshot: Snapshot | None = None
    checked: float = 0
    done: threading.Event = field(default_factory=threading.Event)
    progress: Progress | None = None
    error: str | None = None
    failures: int = 0
    index: DirectoryIndex | None = None
    reconciled: float = 0
    duration: float = 0
    queued: tuple[Callable, bool] | None = None


@dataclass
class Read:
    snapshot: Snapshot | None
    scan: dict

    @property
    def status_code(self) -> int:
        if self.snapshot is not None:
            return 200
        return 202 if self.scan["state"] in {"scanning", "queued", "paused"} else 503


class Store:
    def __init__(self):
        self._lock = threading.Lock()
        self._entries: OrderedDict[tuple, _Entry] = OrderedDict()
        self._threads: set[threading.Thread] = set()
        self._closed = False
        self._paused = False
        self._hub = ChangeHub()
        self._retired = []

    def _start_pending_locked(self) -> None:
        """Bounded admission; first listings take priority over cached refreshes."""
        while not self._closed and not self._paused and len(self._threads) < MAX_WORKERS:
            pending = [(key, entry) for key, entry in self._entries.items() if entry.queued]
            if not pending:
                return
            # FIFO within each priority, independent of repeated HTTP polls.
            key, entry = min(pending, key=lambda item: (
                item[1].snapshot is not None, item[1].progress.started,
            ))
            collect, full = entry.queued
            entry.queued = None
            entry.progress = Progress(key[1])
            thread = threading.Thread(target=self._scan, args=(key, entry, collect, full),
                                      name="workspace-scan", daemon=True)
            self._threads.add(thread)
            try:
                thread.start()
            except RuntimeError:
                self._threads.discard(thread)
                entry.done.set()
                entry.error = "Could not start file scan"
                entry.failures += 1
                entry.checked = time.monotonic()

    def _scan(self, key: tuple, entry: _Entry, collect: Callable[[Progress], Snapshot], full: bool):
        view = None
        try:
            with self._lock:
                retired, self._retired = self._retired, []
            for index in retired:
                index.close()
            view = entry.index.begin(entry.progress, full=full)
            entry.progress.cache = view
            snapshot = collect(entry.progress)
            if entry.progress.cancelled.is_set():
                raise ScanCancelled()
            # Watch retirement may do OS work; never hold the request lock.
            view.commit()
            with self._lock:
                if entry.progress.cancelled.is_set():
                    raise ScanCancelled()
                entry.snapshot = snapshot
                entry.error = None
                entry.failures = 0
                if view.full:
                    entry.reconciled = time.monotonic()
            elapsed = time.monotonic() - entry.progress.started
            if elapsed >= fsguard._timeout_seconds():
                log.info("workspace scan completed root=%s entries=%s elapsed=%.2fs",
                         key[1], entry.progress.visited, elapsed)
        except ScanCancelled:
            if view:
                view.abort()
        except Exception as exc:
            if view:
                view.abort()
            # Log once per scan, not once per waiting browser/endpoint. The
            # last complete snapshot survives a failed refresh.
            log.warning("workspace scan failed root=%s operation=%s path=%s entries=%s: %s",
                        key[1], entry.progress.operation, entry.progress.path,
                        entry.progress.visited, exc, exc_info=not isinstance(exc, OSError))
            with self._lock:
                entry.error = f"Could not read workspace files: {exc}"
                entry.failures += 1
        finally:
            with self._lock:
                entry.checked = time.monotonic()
                entry.duration = entry.checked - entry.progress.started
                entry.done.set()
                self._threads.discard(threading.current_thread())
                self._start_pending_locked()

    def read(self, vault: Path, root: Path, include_dotfiles: bool,
             collect: Callable[[Progress], Snapshot], *, refresh: bool = False) -> Read:
        # Lexical keys only: resolving a path on the request thread could hang
        # before the background worker gets a chance to guard the filesystem.
        key = (str(vault), str(root), include_dotfiles)
        with self._lock:
            if self._closed:
                return Read(None, {"state": "busy", "detail": "File service is stopping"})
            entry = self._entries.get(key)
            if self._paused:
                return Read(entry.snapshot if entry else None,
                            {"state": "paused", "detail": "File scans paused in Resources"})
            if entry is None:
                while len(self._entries) >= MAX_ROOTS:
                    victim = next((k for k, e in self._entries.items() if e.done.is_set()), None)
                    if victim is None:
                        # The bounded scope queue is full. Retry admission; this
                        # is normal backpressure, not a failed filesystem read.
                        return Read(None, {"state": "queued", "detail": "Waiting for a file scan slot"})
                    self._retired.append(self._entries.pop(victim).index)
                entry = _Entry(index=DirectoryIndex(root, include_dotfiles, self._hub))
                entry.done.set()
                self._entries[key] = entry
            self._entries.move_to_end(key)
            age = time.monotonic() - entry.checked
            interval = RECONCILE_SECONDS if entry.index.watching() else FALLBACK_SECONDS
            # Slow/unavailable volumes must get a rest even in fallback mode.
            interval = max(interval, entry.duration * 4)
            full = refresh or time.monotonic() - entry.reconciled >= interval
            pending, changed, first_changed = entry.index.pending()
            quiet = time.monotonic() - changed >= DEBOUNCE_SECONDS or time.monotonic() - first_changed >= MAX_DEBOUNCE_SECONDS
            due = entry.snapshot is None or full or bool(entry.error) or pending and quiet
            if entry.error and age < min(60, 2 ** min(entry.failures, 6)):
                due = False
            if entry.done.is_set() and due:
                entry.done = threading.Event()
                entry.progress = Progress(str(root), operation="waiting for scan slot")
                entry.error = None
                entry.queued = (collect, full)
                self._start_pending_locked()
            done = entry.done
            cached = entry.snapshot is not None

        # Small trees retain synchronous, fresh reads. A slow tree never holds
        # a request worker for the ten-second FS deadline or restarts at it.
        if not cached:
            done.wait(REQUEST_WAIT_SECONDS)
        with self._lock:
            progress = entry.progress
            if entry.queued:
                state = "refreshing" if entry.snapshot is not None else "queued"
            elif entry.done.is_set():
                state = "error" if entry.error else "ready"
            else:
                state = "refreshing" if entry.snapshot is not None else "scanning"
                if time.monotonic() - progress.last_step >= fsguard._timeout_seconds():
                    state = "stalled"
                    if not progress.warned:
                        progress.warned = True
                        log.warning("workspace scan stalled root=%s operation=%s path=%s entries=%s idle=%.2fs",
                                    root, progress.operation, progress.path, progress.visited,
                                    time.monotonic() - progress.last_step)
            status = progress.status(state)
            if entry.error:
                status["detail"] = entry.error
            elif state == "stalled":
                status["detail"] = f"File scan is waiting on {progress.operation}: {progress.path}"
            return Read(entry.snapshot, status)

    def resource_status(self) -> dict:
        """In-memory diagnostics: monitoring must never trigger a file scan."""
        with self._lock:
            scans = []
            for key, entry in self._entries.items():
                if entry.progress and not entry.done.is_set():
                    state = "queued" if entry.queued else "scanning"
                    if entry.progress.cancelled.is_set():
                        state = "stopping"
                    scans.append({"root": key[1], **entry.progress.status(state)})
            return {"paused": self._paused, "scans": scans}

    def pause(self, paused: bool) -> None:
        """Cancel cooperatively and prevent browser polls restarting the work."""
        with self._lock:
            self._paused = paused
            for entry in self._entries.values():
                if paused:
                    if entry.progress:
                        entry.progress.cancelled.set()
                    if entry.queued:
                        entry.queued = None
                        entry.done.set()
                else:
                    entry.reconciled = 0
                    entry.index.invalidate()

    def invalidate_all(self) -> None:
        """Explicit reconciliation hook (also used by materialized test reads)."""
        with self._lock:
            for entry in self._entries.values():
                entry.index.invalidate()
                entry.reconciled = 0

    def close(self) -> None:
        with self._lock:
            self._closed = True
            for entry in self._entries.values():
                if entry.progress:
                    entry.progress.cancelled.set()
                if entry.queued:
                    entry.queued = None
                    entry.done.set()
            threads = list(self._threads)
            self._entries.clear()
        # Cooperative walks exit promptly. A blocked OS call must not prevent
        # shutdown; its daemon worker exits when the syscall finally returns.
        deadline = time.monotonic() + 0.5
        for thread in threads:
            thread.join(max(0, deadline - time.monotonic()))
        self._hub.close()
