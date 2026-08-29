"""Persistent routing for rolling Lab tmux socket generations.

The default tmux socket remains the implicit generation until a user runs
``lab terminal rotate`` from a fresh non-tmux terminal. A rotation keeps the
previous generation discoverable while making the newly seeded server active
for future sessions. There are deliberately at most two generations: one
active and one draining. Once the draining generation has no Lab sessions it
is removed from the routing file, returning steady-state discovery cost to one
tmux command.

This is framework-level runtime state, shared by every registered workspace.
It lives under ``LAB_HOME`` rather than in any workspace's project metadata.
"""
from __future__ import annotations

import fcntl
import json
import os
import re
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from lab import paths


DEFAULT_SOCKET = "default"
STATE_VERSION = 1
_SOCKET_RE = re.compile(r"^[A-Za-z0-9_-]{1,80}$")

_CACHE_PATH: Path | None = None
_CACHE_SIGNATURE: tuple[int, int, int] | None = None
_CACHE_STATE: dict[str, Any] | None = None


def state_file() -> Path:
    return paths.global_config_dir() / "tmux-sockets.json"


@contextmanager
def state_lock() -> Iterator[None]:
    """Serialize rotation and drain-pruning across CLI/backend processes."""
    lock_path = state_file().with_suffix(".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def default_state() -> dict[str, Any]:
    return {
        "version": STATE_VERSION,
        "active": DEFAULT_SOCKET,
        "generations": [
            {"name": DEFAULT_SOCKET, "status": "active", "created_at": 0},
        ],
    }


def valid_socket_name(value: object) -> bool:
    return isinstance(value, str) and bool(_SOCKET_RE.fullmatch(value))


def is_no_server_error(error: str) -> bool:
    """Recognize tmux's platform/version-specific empty-server messages."""
    lowered = error.lower()
    return (
        "no server running" in lowered
        or "no sessions" in lowered
        or (
            "error connecting to" in lowered
            and (
                "no such file or directory" in lowered
                or "connection refused" in lowered
            )
        )
    )


def _normalized(raw: object) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return default_state()
    active = raw.get("active")
    if not valid_socket_name(active):
        return default_state()

    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw.get("generations") or []:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not valid_socket_name(name) or name in seen:
            continue
        status = "active" if name == active else "draining"
        created = item.get("created_at")
        rows.append({
            "name": name,
            "status": status,
            "created_at": int(created) if isinstance(created, (int, float)) else 0,
        })
        seen.add(name)
    if active not in seen:
        rows.append({"name": active, "status": "active", "created_at": 0})

    active_row = next(row for row in rows if row["name"] == active)
    draining = sorted(
        (row for row in rows if row["name"] != active),
        key=lambda row: row["created_at"],
        reverse=True,
    )[:1]
    return {
        "version": STATE_VERSION,
        "active": active,
        "generations": [active_row] + draining,
    }


def _signature(path: Path) -> tuple[int, int, int] | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    # Atomic replacement changes the inode even in the unlikely event that
    # two same-sized writes receive the same filesystem timestamp.
    return stat.st_ino, stat.st_mtime_ns, stat.st_size


def _copy_state(state: dict[str, Any]) -> dict[str, Any]:
    return {
        **state,
        "generations": [dict(row) for row in state["generations"]],
    }


def read_state() -> dict[str, Any]:
    """Read socket routing, caching only while the atomic file is unchanged."""
    global _CACHE_PATH, _CACHE_SIGNATURE, _CACHE_STATE

    path = state_file()
    signature = _signature(path)
    if path == _CACHE_PATH and signature == _CACHE_SIGNATURE and _CACHE_STATE is not None:
        return _copy_state(_CACHE_STATE)
    if signature is None:
        state = default_state()
    else:
        try:
            state = _normalized(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError, json.JSONDecodeError):
            state = default_state()
    _CACHE_PATH = path
    _CACHE_SIGNATURE = signature
    _CACHE_STATE = state
    return _copy_state(state)


def write_state(state: dict[str, Any]) -> Path:
    """Atomically replace routing state so the backend never reads half JSON."""
    global _CACHE_PATH, _CACHE_SIGNATURE, _CACHE_STATE

    normalized = _normalized(state)
    path = state_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(normalized, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
    _CACHE_PATH = path
    _CACHE_SIGNATURE = _signature(path)
    _CACHE_STATE = normalized
    return path


def active_socket() -> str:
    return str(read_state()["active"])


def generations() -> list[dict[str, Any]]:
    return read_state()["generations"]


def socket_names() -> list[str]:
    return [str(row["name"]) for row in generations()]


def command(socket_name: str, *args: str) -> list[str]:
    """Build a tmux argv without changing the default-socket command shape."""
    if not valid_socket_name(socket_name):
        raise ValueError(f"invalid tmux socket name: {socket_name!r}")
    if socket_name == DEFAULT_SOCKET:
        return ["tmux", *args]
    return ["tmux", "-L", socket_name, *args]


def rotated_state(previous: dict[str, Any], new_socket: str) -> dict[str, Any]:
    """Return a two-generation handoff from ``previous`` to ``new_socket``."""
    if not valid_socket_name(new_socket) or new_socket == DEFAULT_SOCKET:
        raise ValueError(f"invalid rotated tmux socket name: {new_socket!r}")
    normalized = _normalized(previous)
    old_active = str(normalized["active"])
    draining = [
        row for row in normalized["generations"] if row["name"] != old_active
    ]
    if draining:
        raise RuntimeError("a previous tmux socket generation is still draining")
    old_created = next(
        (
            int(row.get("created_at") or 0)
            for row in normalized["generations"]
            if row["name"] == old_active
        ),
        0,
    )
    return {
        "version": STATE_VERSION,
        "active": new_socket,
        "generations": [
            {"name": old_active, "status": "draining", "created_at": old_created},
            {"name": new_socket, "status": "active", "created_at": int(time.time())},
        ],
    }


def prune_drained(empty_sockets: set[str], *, already_locked: bool = False) -> bool:
    """Drop a draining generation once no Lab sessions remain on it."""
    def _prune() -> bool:
        state = read_state()
        active = str(state["active"])
        rows = [
            row
            for row in state["generations"]
            if row["name"] == active or row["name"] not in empty_sockets
        ]
        if len(rows) == len(state["generations"]):
            return False
        write_state({
            "version": STATE_VERSION,
            "active": active,
            "generations": rows,
        })
        return True

    if already_locked:
        return _prune()
    with state_lock():
        return _prune()
