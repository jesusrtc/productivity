"""Disk-backed, bounded stale-while-revalidate cache for read-only sidebar data.

Payloads live in the owning vault, not a process-wide dictionary of file trees.
Only requested views are refreshed. Two workers and a bounded admission queue
limit Git/IO pressure, including when several browser tabs are open.
"""
from __future__ import annotations

from collections import OrderedDict
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import sqlite3
import threading
import time
from typing import Callable

TTL = 60
MAX_BYTES = 128 * 1024 * 1024
MAX_ENTRY_BYTES = 64 * 1024 * 1024
MAX_ENTRIES = 256
MAX_JOBS = 32
WORKERS = 2


@dataclass
class Read:
    value: object = None
    updated: float = 0
    pending: bool = False
    error: str = ""

    def metadata(self):
        return {"updated": self.updated, "refreshing": self.pending,
                "stale": time.time() - self.updated >= TTL, "error": self.error}


class Store:
    def __init__(self, workers=WORKERS):
        self._workers = workers
        self._lock = threading.Lock()
        self._jobs = OrderedDict()
        self._active = set()
        self._failures = OrderedDict()
        self._fallback = OrderedDict()  # Used only when disk persistence fails; 2 MiB total.
        self._closed = False

    @staticmethod
    @contextmanager
    def _db(vault: Path):
        folder = vault / ".lab" / "cache"
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = folder / "sidebar-v1.sqlite3"
        new = not path.exists()
        db = sqlite3.connect(path, timeout=.1)
        # DELETE journal avoids an unbounded WAL when browsers read constantly.
        try:
            if new:
                path.chmod(0o600)
            db.execute("CREATE TABLE IF NOT EXISTS snapshots (key TEXT PRIMARY KEY, updated REAL, body BLOB)")
            with db:
                yield db
        finally:
            db.close()

    def _load(self, vault, key, page=None):
        try:
            with self._db(vault) as db:
                if page is not None:
                    offset, sort, hidden, extensions = page
                    row = db.execute("SELECT updated, json_remove(body, '$.entries', '$.files') FROM snapshots WHERE key=?", (key,)).fetchone()
                    if not row:
                        raise LookupError("No persisted snapshot")
                    predicate = "s.key=?"
                    params = [key]
                    if not hidden:
                        predicate += " AND json_extract(e.value, '$.path') NOT LIKE '.%' AND json_extract(e.value, '$.path') NOT LIKE '%/.%'"
                    if extensions:
                        predicate += " AND json_extract(e.value, '$._extension') IN (" + ','.join('?' for _ in extensions) + ")"
                        params.extend(extensions)
                    source = " FROM snapshots s, json_each(s.body, '$.entries') e WHERE " + predicate
                    total = db.execute("SELECT count(*)" + source, params).fetchone()[0]
                    # sort is one of three fixed column expressions, never SQL from a URL.
                    rank = {'name':'_rank_name', 'type':'_rank_type', 'updated':'_rank_updated'}[sort]
                    rows = db.execute("SELECT e.value" + source + f" ORDER BY json_extract(e.value, '$.{rank}') LIMIT 200 OFFSET ?", [*params, offset]).fetchall()
                    data = json.loads(row[1])
                    data.update(entries=[json.loads(item[0]) for item in rows], total=total,
                                next_offset=min(offset + len(rows), total))
                    data['files'] = [entry['path'] for entry in data['entries']]
                    return Read(data, row[0])
                row = db.execute("SELECT updated, json(body) FROM snapshots WHERE key=?", (key,)).fetchone()
            if row:
                return Read(json.loads(row[1]), row[0])
        except (OSError, sqlite3.Error, ValueError, LookupError):
            pass  # A missing/corrupt cache must not prevent a live read.
        with self._lock:
            fallback = self._fallback.get((str(vault), key))
        if fallback:
            data = json.loads(fallback[1])
            if page is not None:
                offset, sort, hidden, extensions = page
                entries = [row for row in data.get('entries', []) if (hidden or not any(p.startswith('.') for p in row['path'].split('/')))
                           and (not extensions or row.get('_extension') in extensions)]
                entries.sort(key=lambda row: row.get('_rank_' + sort, 0))
                data.update(entries=entries[offset:offset+200], total=len(entries), next_offset=min(offset+200,len(entries)))
                data['files'] = [row['path'] for row in data['entries']]
            return Read(data, fallback[0])
        return Read()

    def _save(self, vault, key, value):
        body = json.dumps(value, ensure_ascii=True, separators=(",", ":")).encode()
        if len(body) > MAX_ENTRY_BYTES:
            raise ValueError("Sidebar snapshot exceeds the cache size limit")
        with self._db(vault) as db:
            # Newer SQLite can traverse its binary JSON without reparsing a
            # large recent-file snapshot for each small page. Older installs
            # retain the identical JSON-text contract.
            encoded = "jsonb(?)" if sqlite3.sqlite_version_info >= (3, 45, 0) else "?"
            db.execute(f"INSERT OR REPLACE INTO snapshots VALUES (?, ?, {encoded})", (key, time.time(), body))
            rows = db.execute("SELECT key, length(body) FROM snapshots ORDER BY updated DESC").fetchall()
            size = 0
            for index, (old_key, length) in enumerate(rows):
                size += length
                if index >= MAX_ENTRIES or size > MAX_BYTES:
                    db.execute("DELETE FROM snapshots WHERE key=?", (old_key,))
        # SQLite reuses freed pages. The DB stays at its bounded high-water mark.

    def _start_locked(self):
        while not self._closed and len(self._active) < self._workers:
            groups = {self._jobs[key][2] for key in self._active if self._jobs[key][2] is not None}
            next_job = next((key for key, job in self._jobs.items()
                             if key not in self._active and (job[2] is None or job[2] not in groups)), None)
            if next_job is None:
                return
            self._active.add(next_job)
            threading.Thread(target=self._run, args=(next_job,), daemon=True,
                             name="sidebar-refresh").start()

    def _run(self, identity):
        with self._lock:
            collect, done, _ = self._jobs[identity]
        error = ""
        try:
            value = collect()
            try:
                self._save(Path(identity[0]), identity[1], value)
                with self._lock:
                    self._fallback.pop(identity, None)
            except (OSError, sqlite3.Error):
                body = json.dumps(value, ensure_ascii=True).encode()
                if len(body) > 2 * 1024 * 1024:
                    raise
                with self._lock:
                    self._fallback[identity] = (time.time(), body)
                    self._fallback.move_to_end(identity)
                    while sum(len(row[1]) for row in self._fallback.values()) > 2 * 1024 * 1024:
                        self._fallback.popitem(last=False)
        except Exception as exc:
            error = str(exc)
        finally:
            with self._lock:
                self._jobs.pop(identity, None)
                self._active.discard(identity)
                if error:
                    self._failures[identity] = (time.time(), error)
                    while len(self._failures) > MAX_JOBS:
                        self._failures.popitem(last=False)
                else:
                    self._failures.pop(identity, None)
                done.set()
                self._start_locked()

    def read(self, vault: Path, key: tuple, collect: Callable, *, wait=.15, ttl=TTL, group=None, page=None):
        key_hash = hashlib.sha256(json.dumps(key).encode()).hexdigest()
        identity = (str(vault), key_hash)
        result = self._load(vault, key_hash, page)
        with self._lock:
            failure_time, error = self._failures.get(identity, (0, ""))
            due = time.time() - result.updated >= ttl
            if (due and not self._closed and identity not in self._jobs
                    and len(self._jobs) < MAX_JOBS and time.time() - failure_time >= 5):
                self._jobs[identity] = (collect, threading.Event(), (str(vault), group) if group is not None else None)
                self._start_locked()
            job = self._jobs.get(identity)
        if result.value is None and job and wait:
            job[1].wait(wait)
            result = self._load(vault, key_hash, page)
        with self._lock:
            result.pending = identity in self._jobs or (due and not error and result.value is None)
            result.error = self._failures.get(identity, (0, ""))[1]
        return result

    def peek(self, vault: Path, key: tuple):
        """Read an existing projection without scheduling another job."""
        key_hash = hashlib.sha256(json.dumps(key).encode()).hexdigest()
        return self._load(vault, key_hash)

    def close(self):
        with self._lock:
            self._closed = True
            for key in list(self._jobs):
                if key not in self._active:
                    self._jobs.pop(key)[1].set()
