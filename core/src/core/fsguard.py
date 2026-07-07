"""Fail fast against a stalled workspace volume.

The active Lab workspace can live on removable/networked storage (e.g. a USB
SSD). When that volume wedges, every blocking filesystem call issued against
it (``os.listdir``, ``iterdir``, ``read_text``, ...) can hang for a long time
before eventually raising ``InterruptedError``/``OSError(EINTR)`` -- or just
never return. Left unguarded, a single request against a stalled directory
walk (e.g. the project-files sidebar scan) blocks that worker indefinitely
and the UI just spins.

``guarded()`` runs a blocking filesystem operation on a small worker pool
with a timeout. If the operation doesn't finish in time, or fails with the
EINTR signature of a stalled volume, it raises a 503 ``HTTPException`` naming
the affected workspace instead of hanging the request.
"""
from __future__ import annotations

import errno
import logging
import os
import threading
import tomllib
from concurrent.futures import ThreadPoolExecutor
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


def _timeout_seconds() -> float:
    raw = os.environ.get("LAB_FS_TIMEOUT_SECONDS")
    if raw:
        try:
            return float(raw)
        except ValueError:
            pass
    return DEFAULT_TIMEOUT_SECONDS


def _workspaces_toml_path() -> Path:
    if _lab_paths is not None:
        return _lab_paths.workspaces_file()
    return Path(os.environ.get("LAB_HOME", "~/.lab")).expanduser() / "workspaces.toml"


def workspace_name(root: Path) -> str:
    """Resolve a human-readable display name for the workspace at ``root``.

    Resolution order (read fresh on every call -- the registry can change,
    e.g. workspace ids being renamed, while the server keeps running):

      1. Match ``root`` (resolved) against ``[[workspaces]]`` entries in
         ``~/.lab/workspaces.toml`` by resolved ``path``; use that row's
         ``name`` (falling back to its ``id``).
      2. ``[workspace].name`` in ``{root}/lab.toml``.
      3. The directory name of ``root``.
    """
    resolved = Path(root).expanduser().resolve()

    registry_path = _workspaces_toml_path()
    if registry_path.is_file():
        try:
            data = tomllib.loads(registry_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        for row in data.get("workspaces") or []:
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
            name = (data.get("workspace") or {}).get("name")
            if name:
                return str(name)
        except (OSError, ValueError):
            pass

    return resolved.name


def _unavailable(root: Path) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail=f"resource is not available for workspace {workspace_name(root)}",
    )


def _describe_op(fn: Callable, args: tuple) -> str:
    """Best-effort human-readable label for what ``guarded()`` was running --
    used only for the error log line, e.g. ``scan(/path/to/project)``."""
    name = getattr(fn, "__qualname__", None) or getattr(fn, "__name__", None) or repr(fn)
    if args and isinstance(args[0], (str, Path)):
        return f"{name}({args[0]})"
    return name


def _run_tracked(fn: Callable[..., T], args: tuple, kwargs: dict) -> T:
    global _inflight
    try:
        return fn(*args, **kwargs)
    finally:
        with _inflight_lock:
            _inflight -= 1


def guarded(root: Path, fn: Callable[..., T], *args, timeout: float | None = None, **kwargs) -> T:
    """Run ``fn(*args, **kwargs)`` on the bounded fsguard worker pool.

    Raises ``fastapi.HTTPException(503, ...)`` naming ``root``'s workspace
    if the call doesn't finish within ``timeout`` seconds (default from the
    ``LAB_FS_TIMEOUT_SECONDS`` env var, else 10s), if it raises
    ``InterruptedError`` / an ``OSError`` with ``errno.EINTR`` (the signature
    of a stalled volume), or if the pool is already saturated with other
    stuck calls.

    On timeout the worker thread is deliberately leaked -- there is no way
    to cancel a blocking syscall from Python -- which is why the pool is
    bounded: repeated timeouts occupy at most ``_MAX_WORKERS`` threads total,
    they don't accumulate one per request.
    """
    global _inflight
    with _inflight_lock:
        if _inflight >= _MAX_WORKERS:
            raise _unavailable(root)
        _inflight += 1

    try:
        future = _executor.submit(_run_tracked, fn, args, kwargs)
    except RuntimeError:
        # Executor rejected the submission (e.g. shutting down) -- release
        # the slot we reserved above and fail the same way a stall would.
        with _inflight_lock:
            _inflight -= 1
        raise _unavailable(root)

    effective_timeout = timeout if timeout is not None else _timeout_seconds()
    try:
        return future.result(timeout=effective_timeout)
    except FutureTimeoutError:
        log.error(
            "fs timeout after %ss reading %s (workspace %s)",
            effective_timeout, _describe_op(fn, args), workspace_name(root),
        )
        raise _unavailable(root)
    except (InterruptedError, OSError) as exc:
        if isinstance(exc, InterruptedError) or getattr(exc, "errno", None) == errno.EINTR:
            log.error(
                "fs EINTR reading %s (workspace %s): %s",
                _describe_op(fn, args), workspace_name(root), exc,
            )
            raise _unavailable(root)
        raise
