"""Fail fast against a stalled vault volume.

The active Lab vault can live on removable/networked storage (e.g. a USB
SSD). When that volume wedges, every blocking filesystem call issued against
it (``os.listdir``, ``iterdir``, ``read_text``, ...) can hang for a long time
before eventually raising ``InterruptedError``/``OSError(EINTR)`` -- or just
never return. Left unguarded, a single request against a stalled directory
walk (e.g. the workspace-files sidebar scan) blocks that worker indefinitely
and the UI just spins.

``guarded()`` runs a blocking filesystem operation on a small worker pool
with a timeout. If the operation doesn't finish in time, or fails with the
EINTR signature of a stalled volume, it raises a 503 ``HTTPException`` naming
the affected vault instead of hanging the request.
"""
from __future__ import annotations

import errno
import logging
import os
import threading
import tomllib
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from pathlib import Path
from typing import Callable, TypeVar

from fastapi import HTTPException

try:
    from lab import paths as _lab_paths
except ImportError:  # pragma: no cover - `lab` is always on PYTHONPATH in prod
    _lab_paths = None


log = logging.getLogger(__name__)

T = TypeVar("T")

DEFAULT_TIMEOUT_SECONDS = 10.0

# Bounded so a stalled volume can only ever leak a handful of stuck threads,
# not one per request. Module-level + shared across every guarded() call.
_MAX_WORKERS = 4
_executor = ThreadPoolExecutor(max_workers=_MAX_WORKERS, thread_name_prefix="fsguard")

# Tracks worker slots actually occupied by a *running* blocking call (as
# opposed to "submitted to the executor"). A slot is freed only when the
# wrapped function returns/raises for real -- a timed-out caller gives up on
# `future.result()` but the underlying thread (and its slot) keeps running,
# which is exactly how a permanently wedged volume should show up: the pool
# fills up and every subsequent call fails fast instead of queuing behind
# calls that will never finish.
_inflight_lock = threading.Lock()
_inflight = 0
_operations: dict[tuple, tuple[Future, threading.Event]] = {}
_worker_state = threading.local()


class _CancelledRead(RuntimeError):
    pass


def checkpoint() -> None:
    """Stop a timed-out walk between syscalls, releasing its worker slot."""
    cancelled = getattr(_worker_state, "cancelled", None)
    if cancelled is not None and cancelled.is_set():
        raise _CancelledRead()


def _timeout_seconds() -> float:
    raw = os.environ.get("LAB_FS_TIMEOUT_SECONDS")
    if raw:
        try:
            return float(raw)
        except ValueError:
            pass
    return DEFAULT_TIMEOUT_SECONDS


def _vaults_toml_path() -> Path:
    if _lab_paths is not None:
        return _lab_paths.vaults_file()
    return Path(os.environ.get("LAB_HOME", "~/.lab")).expanduser() / "vaults.toml"


def vault_name(root: Path) -> str:
    """Resolve a human-readable display name for the vault at ``root``.

    Resolution order (read fresh on every call -- the registry can change,
    e.g. vault ids being renamed, while the server keeps running):

      1. Match ``root`` (resolved) against ``[[vaults]]`` entries in
         ``~/.lab/vaults.toml`` by resolved ``path``; use that row's
         ``name`` (falling back to its ``id``).
      2. ``[vault].name`` in ``{root}/lab.toml``.
      3. The directory name of ``root``.
    """
    resolved = Path(root).expanduser().resolve()

    registry_path = _vaults_toml_path()
    if registry_path.is_file():
        try:
            data = tomllib.loads(registry_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        for row in data.get("vaults") or []:
            if not isinstance(row, dict):
                continue
            row_path = row.get("path")
            if not row_path:
                continue
            try:
                if Path(str(row_path)).expanduser().resolve() == resolved:
                    name = row.get("name") or row.get("id")
                    if name:
                        return str(name)
            except OSError:
                continue

    lab_toml = resolved / "lab.toml"
    if lab_toml.is_file():
        try:
            data = tomllib.loads(lab_toml.read_text(encoding="utf-8"))
            name = (data.get("vault") or {}).get("name")
            if name:
                return str(name)
        except (OSError, ValueError):
            pass

    return resolved.name


def _unavailable(root: Path) -> HTTPException:
    # Never resolve paths or read a registry on this error path: the volume
    # may be stuck, or the process may have no descriptors left to open it.
    return HTTPException(
        status_code=503,
        detail=f"resource is not available for vault {Path(root).name}",
        headers={"Retry-After": "2"},
    )


def _describe_op(fn: Callable, args: tuple) -> str:
    """Best-effort human-readable label for what ``guarded()`` was running --
    used only for the error log line, e.g. ``scan(/path/to/workspace)``."""
    name = getattr(fn, "__qualname__", None) or getattr(fn, "__name__", None) or repr(fn)
    if args and isinstance(args[0], (str, Path)):
        return f"{name}({args[0]})"
    return name


def _run_tracked(fn: Callable[..., T], args: tuple, kwargs: dict,
                 cancelled: threading.Event, key: tuple | None) -> T:
    global _inflight
    _worker_state.cancelled = cancelled
    try:
        checkpoint()
        return fn(*args, **kwargs)
    finally:
        _worker_state.cancelled = None
        with _inflight_lock:
            _inflight -= 1
            if key is not None:
                _operations.pop(key, None)


def guarded(root: Path, fn: Callable[..., T], *args, timeout: float | None = None,
            operation_key: tuple | None = None, **kwargs) -> T:
    """Run ``fn(*args, **kwargs)`` on the bounded fsguard worker pool.

    Raises ``fastapi.HTTPException(503, ...)`` naming ``root``'s vault
    if the call doesn't finish within ``timeout`` seconds (default from the
    ``LAB_FS_TIMEOUT_SECONDS`` env var, else 10s), if it raises
    ``InterruptedError`` / an ``OSError`` with ``errno.EINTR`` (the signature
    of a stalled volume), or if the pool is already saturated with other
    stuck calls.

    Callers may share an operation_key for identical read-only work. The key
    remains reserved until the worker exits, even after a caller times out.
    Walks should call checkpoint() between syscalls so abandoned work stops.
    A blocked syscall itself cannot be cancelled, so the pool remains bounded.
    """
    global _inflight
    key = (str(root), operation_key) if operation_key is not None else None
    with _inflight_lock:
        existing = _operations.get(key) if key is not None else None
        if existing is not None:
            future, cancelled = existing
            if cancelled.is_set():
                raise _unavailable(root)
        else:
            if _inflight >= _MAX_WORKERS:
                raise _unavailable(root)
            _inflight += 1
            cancelled = threading.Event()
            try:
                future = _executor.submit(_run_tracked, fn, args, kwargs, cancelled, key)
            except RuntimeError:
                _inflight -= 1
                raise _unavailable(root)
            if key is not None:
                _operations[key] = (future, cancelled)

    effective_timeout = timeout if timeout is not None else _timeout_seconds()
    try:
        return future.result(timeout=effective_timeout)
    except (FutureTimeoutError, _CancelledRead):
        with _inflight_lock:
            first_timeout = not cancelled.is_set()
            cancelled.set()
        if first_timeout:
            log.error(
                "fs timeout after %ss reading %s (vault %s)",
                effective_timeout, _describe_op(fn, args), Path(root).name,
            )
        raise _unavailable(root)
    except (InterruptedError, OSError) as exc:
        if isinstance(exc, InterruptedError) or getattr(exc, "errno", None) in {errno.EINTR, errno.EMFILE, errno.ENFILE}:
            log.error(
                "fs %s reading %s (vault %s): %s",
                errno.errorcode.get(exc.errno, "EINTR"), _describe_op(fn, args), Path(root).name, exc,
            )
            raise _unavailable(root)
        raise
