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


log = logging.getLogger(__name__)
REQUEST_WAIT_SECONDS = 0.15
REFRESH_SECONDS = 2.0
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


@dataclass
class Read:
    snapshot: Snapshot | None
    scan: dict

    @property
    def status_code(self) -> int:
        if self.snapshot is not None:
            return 200
        return 202 if self.scan["state"] == "scanning" else 503


class Store:
    def __init__(self):
        self._lock = threading.Lock()
        self._entries: OrderedDict[tuple, _Entry] = OrderedDict()
        self._threads: set[threading.Thread] = set()
        self._closed = False

    def _scan(self, key: tuple, entry: _Entry, collect: Callable[[Progress], Snapshot]):
        try:
            snapshot = collect(entry.progress)
            with self._lock:
                entry.snapshot = snapshot
                entry.error = None
                entry.failures = 0
            elapsed = time.monotonic() - entry.progress.started
            if elapsed >= fsguard._timeout_seconds():
                log.info("workspace scan completed root=%s entries=%s elapsed=%.2fs",
                         key[1], entry.progress.visited, elapsed)
        except ScanCancelled:
            pass
        except Exception as exc:
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
                entry.done.set()
                self._threads.discard(threading.current_thread())

    def read(self, vault: Path, root: Path, include_dotfiles: bool,
             collect: Callable[[Progress], Snapshot], *, refresh: bool = False) -> Read:
        # Lexical keys only: resolving a path on the request thread could hang
        # before the background worker gets a chance to guard the filesystem.
        key = (str(vault), str(root), include_dotfiles)
        with self._lock:
            if self._closed:
                return Read(None, {"state": "busy", "detail": "File service is stopping"})
            entry = self._entries.get(key)
            if entry is None:
                while len(self._entries) >= MAX_ROOTS:
                    victim = next((k for k, e in self._entries.items() if e.done.is_set()), None)
                    if victim is None:
                        return Read(None, {"state": "busy", "detail": "File scans are busy"})
                    del self._entries[victim]
                entry = _Entry()
                entry.done.set()
                self._entries[key] = entry
            self._entries.move_to_end(key)
            age = time.monotonic() - entry.checked
            interval = max(REFRESH_SECONDS, min(60, 2 ** min(entry.failures, 6))) if entry.error else REFRESH_SECONDS
            due = entry.progress is None or age >= interval or refresh and not entry.error
            busy = False
            if entry.done.is_set() and due:
                if len(self._threads) >= MAX_WORKERS:
                    busy = True  # No executor queue behind a stuck volume.
                else:
                    entry.done = threading.Event()
                    entry.progress = Progress(str(root))
                    entry.error = None
                    thread = threading.Thread(target=self._scan, args=(key, entry, collect),
                                              name="workspace-scan", daemon=True)
                    self._threads.add(thread)
                    try:
                        thread.start()
                    except RuntimeError:
                        self._threads.discard(thread)
                        entry.done.set()
                        entry.error = "Could not start file scan"
                        entry.checked = time.monotonic()
            done = entry.done

        # Small trees retain synchronous, fresh reads. A slow tree never holds
        # a request worker for the ten-second FS deadline or restarts at it.
        done.wait(REQUEST_WAIT_SECONDS)
        with self._lock:
            if busy:
                return Read(entry.snapshot, {"state": "busy", "detail": "File scans are busy"})
            progress = entry.progress
            if entry.done.is_set():
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

    def close(self) -> None:
        with self._lock:
            self._closed = True
            for entry in self._entries.values():
                if entry.progress:
                    entry.progress.cancelled.set()
            threads = list(self._threads)
            self._entries.clear()
        # Cooperative walks exit promptly. A blocked OS call must not prevent
        # shutdown; its daemon worker exits when the syscall finally returns.
        deadline = time.monotonic() + 0.5
        for thread in threads:
            thread.join(max(0, deadline - time.monotonic()))
