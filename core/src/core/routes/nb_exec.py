"""Execute code in the kernel pinned to a repository ``.ipynb`` notebook.

This is the single execution/write path the UI and agents both use:

    POST /api/nb/exec   { "path": "...rel.ipynb", "code": "...", "kernel": "python3" }

The endpoint:

1. Validates that ``path`` is a workspace-relative notebook path.
2. Writes the created/modified cell with actor identity and a running marker.
3. Executes on the configured local Jupyter kernel, or the legacy Darwin
   provider when a project runtime has not been configured.
4. Streams ordered execution-count, text, rich-display, display-update, clear,
   error, and terminal events to every open Lab view.
5. Atomically checkpoints partial output for restart recovery, then replaces the
   running cell with its final nbformat outputs.

The notebook file is the durable record. ``GET /api/nb/live`` supplies an
in-memory replay snapshot to browsers that open or reconnect during a run.
"""
from __future__ import annotations

import asyncio
import base64
import copy
import hashlib
import json
import os
import shlex
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from core import auth
from core.diff_parser import parse_notebook, parse_notebook_output
from core.notebook_runtime import (
    RuntimeBuildError,
    RuntimeConfigError,
    active_runtime,
    load_runtime_spec,
)
from core.state import NotebookExecutionEvent


router = APIRouter()


# ── Path safety (shared shape with routes/notebook.py) ───────────────────────

def _safe_resolve(root: Path, rel: str) -> Path:
    if not rel:
        raise HTTPException(status_code=400, detail="path is required")
    if rel.startswith("/"):
        raise HTTPException(status_code=400, detail="absolute paths not allowed")
    if ".." in Path(rel).parts:
        raise HTTPException(status_code=400, detail="path traversal not allowed")
    if not rel.lower().endswith(".ipynb"):
        raise HTTPException(status_code=400, detail="only .ipynb files supported")
    target = (root / rel).resolve()
    rroot = root.resolve()
    if rroot not in target.parents and target != rroot:
        raise HTTPException(status_code=400, detail="path escapes monorepo")
    return target


# ── Session naming ───────────────────────────────────────────────────────────
# A deterministic 12-char hex digest of the relative path keeps the kernel
# pinned to the file: same path → same Darwin session → same kernel state.

def _session_for(rel_path: str) -> str:
    digest = hashlib.sha1(rel_path.encode("utf-8")).hexdigest()[:12]
    return f"lab-{digest}"


def _configured_local(root: Path, rel_path: str) -> bool:
    try:
        spec = load_runtime_spec(root, rel_path)
    except RuntimeConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return spec is not None and spec.mode == "local"


def _required_local_handle(root: Path, rel_path: str):
    try:
        handle = active_runtime(root, rel_path)
    except (RuntimeBuildError, RuntimeConfigError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if handle is None:
        raise HTTPException(status_code=409, detail="project runtime is not configured for local execution")
    return handle


# ── Per-path write lock ──────────────────────────────────────────────────────
# Two concurrent execs to the same file would race on the JSON read-modify-
# write. The lock is held only across each local file mutation, not while a
# kernel is executing. Each provider serializes work on the path-pinned session.

_path_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _lock_for(target: Path) -> threading.Lock:
    key = str(target)
    with _locks_guard:
        lock = _path_locks.get(key)
        if lock is None:
            lock = threading.Lock()
            _path_locks[key] = lock
    return lock


# ── content/code → Darwin sync ───────────────────────────────────────────────
# Local `content/code/` is treated as a Python package the Darwin kernel can
# import. On the first /api/nb/exec call per session we:
#   1. install lipy-davi (best-effort), and
#   2. prepend ~ to sys.path (parent of the `code` package)
# so cells can do `from code.hello import greet` with no preamble. Edits to
# files under content/code are diffed by mtime on each exec call, written
# directly to the pod's filesystem at `~/code/...` via `darwin pod shell`,
# and the corresponding modules are `importlib.reload()`-ed so cells pick
# up new behavior without a kernel restart.
#
# We deliberately use `darwin pod shell` (writes to the kernel filesystem)
# instead of `darwin file upload` (writes to the Jupyter Contents API
# namespace, which the kernel cannot read from). They are separate stores
# on Darwin pods.
#
# None of this runs when `content/code/` does not exist locally — existing
# notebooks are unaffected.

_CODE_REL = "content/code"
_POD_CODE_DIR = "/home/jovyan/code"

_bootstrapped: set[str] = set()
_bootstrap_guard = threading.Lock()

_mtime_cache: dict[str, float] = {}
_mtime_guard = threading.Lock()


def _code_dir(root: Path) -> Path:
    return root / _CODE_REL


def _list_code_files(root: Path) -> list[Path]:
    code_dir = _code_dir(root)
    if not code_dir.is_dir():
        return []
    return sorted(p for p in code_dir.rglob("*.py") if p.is_file())


def _pod_dest_for(local: Path, code_dir: Path) -> str:
    rel = local.relative_to(code_dir).as_posix()
    return f"{_POD_CODE_DIR}/{rel}"


def _module_for(local: Path, code_dir: Path) -> str | None:
    """Map a local .py file to the dotted module name a cell would import.

    ``content/code/hello.py``         → ``code.hello``
    ``content/code/sub/util.py``      → ``code.sub.util``
    ``content/code/__init__.py``      → ``code`` (the package itself)
    ``content/code/sub/__init__.py``  → ``code.sub``
    """
    rel = local.relative_to(code_dir).with_suffix("")
    parts = ["code"] + [p for p in rel.parts if p != "__init__"]
    if not parts:
        return None
    return ".".join(parts)


def _bootstrap_needed(session: str) -> bool:
    with _bootstrap_guard:
        if session in _bootstrapped:
            return False
        _bootstrapped.add(session)
        return True


def _bootstrap_unmark(session: str) -> None:
    """Forget a session's bootstrap status so the next call retries.

    Used when bootstrap exec itself failed — a transient Darwin error
    shouldn't permanently lock out a session.
    """
    with _bootstrap_guard:
        _bootstrapped.discard(session)


# ── In-memory pending tracker ────────────────────────────────────────────────
# The sidebar polls /api/project-files to decide which notebooks should show
# a green "running" dot. We used to detect that by substring-scanning each
# .ipynb on disk for `"lab_pending": true`, but Plotly-heavy notebooks easily
# exceed any cheap size cap. Track the set of in-flight runs in memory: it's
# O(1), survives no file races, and naturally clears on server restart (the
# Darwin subprocess also dies on restart, so consistent).

_pending_paths: dict[str, int] = {}
_pending_guard = threading.Lock()


def _mark_running(target: Path) -> None:
    key = str(target.resolve())
    with _pending_guard:
        _pending_paths[key] = _pending_paths.get(key, 0) + 1


def _mark_done(target: Path) -> None:
    key = str(target.resolve())
    with _pending_guard:
        remaining = _pending_paths.get(key, 0) - 1
        if remaining > 0:
            _pending_paths[key] = remaining
        else:
            _pending_paths.pop(key, None)


def is_path_pending(target: Path) -> bool:
    with _pending_guard:
        return _pending_paths.get(str(target.resolve()), 0) > 0


# ── Live execution snapshots ────────────────────────────────────────────────
# WebSocket events carry small deltas, while this registry provides a complete
# snapshot to a browser that opens or reconnects midway through a cell. The
# final .ipynb remains authoritative after completion.

_live_runs: dict[tuple[str, str], dict[str, Any]] = {}
_live_guard = threading.Lock()
_LIVE_CHECKPOINT_INTERVAL_S = 0.75


def _live_key(target: Path, run_id: str) -> tuple[str, str]:
    return str(target.resolve()), run_id


def _running_placeholder_output(provider_label: str) -> tuple[dict[str, Any], dict[str, Any]]:
    raw = {
        "output_type": "stream",
        "name": "stdout",
        "text": [f"⏳ Running on {provider_label}…\n"],
    }
    parsed = parse_notebook_output(raw) or {"type": "text", "content": raw["text"][0]}
    return raw, parsed


def _live_start(
    target: Path,
    *,
    path: str,
    workspace: str,
    run_id: str,
    cell_id: str,
    cell_index: int,
    actor: str,
    source: str,
    provider: str,
    provider_label: str,
    execution_count: int,
    started_at: float,
) -> dict[str, Any]:
    raw, parsed = _running_placeholder_output(provider_label)
    state = {
        "path": path,
        "workspace": workspace,
        "run_id": run_id,
        "cell_id": cell_id,
        "cell_index": cell_index,
        "actor": actor,
        "source": source,
        "provider": provider,
        "execution_count": execution_count,
        "started_at": started_at,
        "sequence": 0,
        "outputs": [parsed],
        "raw_outputs": [raw],
        "has_kernel_output": False,
        "last_checkpoint_at": 0.0,
    }
    with _live_guard:
        _live_runs[_live_key(target, run_id)] = state
    return {
        key: copy.deepcopy(value)
        for key, value in state.items()
        if key not in {"raw_outputs", "has_kernel_output", "last_checkpoint_at"}
    }


def _display_id(output: dict[str, Any] | None) -> str:
    if not output:
        return ""
    return str(output.get("display_id") or (output.get("transient") or {}).get("display_id") or "")


def _replace_display(outputs: list[dict[str, Any]], output: dict[str, Any]) -> bool:
    wanted = _display_id(output)
    if not wanted:
        return False
    for index, existing in enumerate(outputs):
        if _display_id(existing) == wanted:
            outputs[index] = output
            return True
    return False


def _live_apply_kernel_event(
    target: Path,
    run_id: str,
    kernel_event: dict[str, Any],
) -> tuple[dict[str, Any] | None, list[dict[str, Any]] | None, int | None]:
    """Apply one ordered kernel event and return WS + optional checkpoint data."""
    with _live_guard:
        state = _live_runs.get(_live_key(target, run_id))
        if state is None:
            return None, None, None
        state["sequence"] += 1
        kind = kernel_event.get("kind")
        operation = kernel_event.get("operation")
        reset = False
        parsed_output: dict[str, Any] | None = None

        if kind == "execution_count":
            value = kernel_event.get("execution_count")
            if isinstance(value, int):
                state["execution_count"] = value
        elif kind == "clear":
            reset = not state["has_kernel_output"]
            state["has_kernel_output"] = True
            state["outputs"] = []
            state["raw_outputs"] = []
            operation = "clear"
        elif kind == "output":
            raw_output = copy.deepcopy(kernel_event.get("output") or {})
            parsed_output = parse_notebook_output(raw_output)
            if not state["has_kernel_output"]:
                state["outputs"] = []
                state["raw_outputs"] = []
                state["has_kernel_output"] = True
                reset = True
            if operation == "replace":
                raw_replaced = _replace_display(state["raw_outputs"], raw_output)
                parsed_replaced = bool(parsed_output) and _replace_display(state["outputs"], parsed_output)
                if not raw_replaced:
                    state["raw_outputs"].append(raw_output)
                if parsed_output is not None and not parsed_replaced:
                    state["outputs"].append(parsed_output)
                    operation = "append"
            else:
                state["raw_outputs"].append(raw_output)
                if parsed_output is not None:
                    state["outputs"].append(parsed_output)
                operation = "append"
        else:
            return None, None, None

        now = time.monotonic()
        force_checkpoint = (
            reset
            or operation in {"clear", "replace"}
            or (parsed_output is not None and parsed_output.get("type") in {"html", "image", "error"})
        )
        checkpoint = None
        if kind != "execution_count" and (
            force_checkpoint
            or now - state["last_checkpoint_at"] >= _LIVE_CHECKPOINT_INTERVAL_S
        ):
            state["last_checkpoint_at"] = now
            checkpoint = copy.deepcopy(state["raw_outputs"])

        payload = {
            "phase": "output" if kind != "execution_count" else "execution-count",
            "path": state["path"],
            "run_id": state["run_id"],
            "cell_id": state["cell_id"],
            "cell_index": state["cell_index"],
            "actor": state["actor"],
            "provider": state["provider"],
            "sequence": state["sequence"],
            "execution_count": state["execution_count"],
            "operation": operation,
            "reset": reset,
        }
        if parsed_output is not None:
            payload["output"] = copy.deepcopy(parsed_output)
        return payload, checkpoint, state["execution_count"]


def _live_snapshot(target: Path) -> list[dict[str, Any]]:
    target_key = str(target.resolve())
    with _live_guard:
        rows = []
        for (path_key, _run_id), state in _live_runs.items():
            if path_key != target_key:
                continue
            rows.append({
                key: copy.deepcopy(value)
                for key, value in state.items()
                if key not in {"raw_outputs", "has_kernel_output", "last_checkpoint_at"}
            })
    return sorted(rows, key=lambda row: (row["started_at"], row["cell_index"]))


def _live_remove(target: Path, run_id: str) -> None:
    with _live_guard:
        _live_runs.pop(_live_key(target, run_id), None)


async def _publish_notebook_event(request: Request, payload: dict[str, Any]) -> None:
    await request.app.state.ws_broadcaster.publish(NotebookExecutionEvent(payload))


# ── Darwin invocation ────────────────────────────────────────────────────────

class _DarwinError(Exception):
    """Raised when the darwin CLI itself fails (auth, pod, missing binary)."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


async def _darwin_exec(
    code: str, *, session: str, kernel: str | None, timeout: int
) -> dict[str, Any]:
    """Run ``darwin code execute`` and return the parsed JSON envelope.

    Code is passed via a temp file (``--file``) so we never have to worry about
    shell quoting for multi-line snippets, embedded quotes, or backslashes.

    The subprocess runs in a thread (``asyncio.to_thread``) so a slow darwin
    call — most notably the multi-minute wait when the kernel is dead — does
    not block the FastAPI event loop. Without this, an unresponsive kernel
    would stall every other request (including ``GET /``).
    """
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(code)
        tmp = f.name
    try:
        cmd = ["darwin", "code", "execute", "--file", tmp, "--session", session]
        if kernel:
            cmd += ["--kernel", kernel]
        if timeout:
            cmd += ["--timeout", str(timeout)]
        try:
            proc = await asyncio.to_thread(
                subprocess.run,
                cmd, capture_output=True, text=True, timeout=timeout + 30,
            )
        except FileNotFoundError as exc:
            raise _DarwinError(
                503, "`darwin` CLI not found on PATH — install the darwin-cli plugin"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise _DarwinError(504, f"darwin timed out after {exc.timeout}s") from exc

        if proc.returncode == 0:
            try:
                return json.loads(proc.stdout)
            except json.JSONDecodeError as exc:
                raise _DarwinError(
                    502,
                    "darwin returned non-JSON output (stdout: "
                    + proc.stdout[:300] + ")",
                ) from exc

        # Exit 6 = KernelExecutionError — the kernel raised before finishing
        # the cell (unimported magic, syntax error, etc.). Darwin emits a
        # structured JSON envelope on stdout. Surface it as an nbformat
        # 'error' output so the cell renders the failure inline (same big
        # red block as a normal Python exception) instead of bubbling a
        # 500 the user has to dig out of devtools.
        if proc.returncode == 6:
            try:
                payload = json.loads(proc.stdout)
            except json.JSONDecodeError:
                payload = {
                    "error": "KernelExecutionError",
                    "message": (proc.stdout or proc.stderr or "")[:500],
                }
            ename = payload.get("error", "KernelExecutionError")
            evalue = payload.get("message", "")
            recovery = payload.get("recovery", "")
            tb = [evalue] + ([recovery] if recovery else [])
            return {
                "output": "",
                "kernel_id": None,
                "execution_count": None,
                "cell_outputs": [{
                    "output_type": "error",
                    "ename": ename,
                    "evalue": evalue,
                    "traceback": tb,
                }],
            }

        # Map a few well-known exit codes to actionable messages. The CLI
        # documents these in its skill; we lean on them so the UI can show
        # something useful instead of "exit 2".
        err_tail = (proc.stderr or proc.stdout or "")[-500:]
        if proc.returncode == 2:
            raise _DarwinError(401, "darwin auth expired — run `darwin auth setup`")
        if proc.returncode == 5:
            raise _DarwinError(503, "darwin pod not ready (cold start can take 2 min)")
        if proc.returncode == 7:
            raise _DarwinError(
                503, "darwin kernel connection lost — run `darwin session clear`"
            )
        raise _DarwinError(
            500, f"darwin failed (exit {proc.returncode}): {err_tail.strip()}"
        )
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


# ── Bootstrap / push / reload helpers (content/code → pod) ───────────────────
# Each helper runs hidden — its output never makes it into the user's
# notebook cell. They share the same `--session` as the user's exec, so
# sys.path and module-import state persist across calls on the same
# kernel. Failures in push/bootstrap surface as _DarwinError so the
# pending-cell error path in exec_cell handles them uniformly. Reload is
# best-effort: if it fails the cell still runs (it'll just see stale
# module state, which is no worse than not having the feature at all).

_BOOTSTRAP_CODE = (
    "import sys, pathlib, subprocess\n"
    # sys.path points at the *parent* of the `code` package on the pod
    # (Path.home(), since files are uploaded to {user}/code/... which
    # resolves to /home/jovyan/{user}/code/...). Pointing at the
    # package itself would make `import code` fall through to the
    # stdlib `code` module — which exists, isn't a package, and breaks
    # `from code.X import Y`.
    "_parent = str(pathlib.Path.home())\n"
    "if _parent not in sys.path:\n"
    "    sys.path.insert(0, _parent)\n"
    # Defensive: if anything imported the stdlib `code` module before
    # the bootstrap ran, evict it so our package wins on the next
    # import. Stdlib `code` has no __path__; our package does.
    "_m = sys.modules.get('code')\n"
    "if _m is not None and not hasattr(_m, '__path__'):\n"
    "    del sys.modules['code']\n"
    "try:\n"
    "    import davi  # noqa: F401\n"
    "except Exception:\n"
    "    subprocess.run(\n"
    "        [sys.executable, '-m', 'pip', 'install', '-q', 'lipy-davi'],\n"
    "        check=False,\n"
    "    )\n"
)


async def _exec_bootstrap(session: str, kernel: str | None) -> None:
    """Run the one-shot setup on this kernel session.

    Idempotent: re-running is harmless (sys.path check is a no-op,
    lipy-davi install short-circuits when already present).
    """
    # Cold-pod + first-time `pip install lipy-davi` can easily take 5+ min;
    # the bootstrap timeout has to absorb that or the user sees a useless
    # "darwin timed out after 210s" on their first cell.
    await _darwin_exec(
        _BOOTSTRAP_CODE, session=session, kernel=kernel, timeout=900
    )


async def _push_code(root: Path) -> list[str]:
    """Write any new/modified files under content/code/ to the pod's kernel
    filesystem at ``/home/jovyan/code/``.

    Returns the list of dotted module names that were re-uploaded — the
    caller uses this to drive a hidden ``importlib.reload`` so cells
    pick up the new code without a kernel restart.

    On the first call for a process the mtime cache is empty, so every
    file looks "new" and gets written once. Subsequent calls only push
    files whose local mtime advanced since the last successful write.

    Files are streamed via ``darwin pod shell`` + base64 to avoid shell
    escaping pitfalls and to bypass the Jupyter Contents API (which is
    a separate namespace from the kernel's filesystem on Darwin pods).
    """
    code_dir = _code_dir(root)
    if not code_dir.is_dir():
        return []
    pushed_modules: list[str] = []
    for local in _list_code_files(root):
        key = str(local.resolve())
        try:
            mtime = local.stat().st_mtime
            content = local.read_bytes()
        except OSError:
            continue
        with _mtime_guard:
            prev = _mtime_cache.get(key)
        if prev is not None and mtime <= prev:
            continue
        dest = _pod_dest_for(local, code_dir)
        parent = os.path.dirname(dest) or "/"
        b64 = base64.b64encode(content).decode("ascii")
        # echo … | base64 -d > dest. `mkdir -p` makes nested packages
        # land in the right place. shlex-quote both the directory and the
        # base64 blob so weird path chars + the `=` padding in base64 are
        # passed literally.
        bash = (
            f"mkdir -p {shlex.quote(parent)} && "
            f"printf '%s' {shlex.quote(b64)} | base64 -d > {shlex.quote(dest)}"
        )
        cmd = ["darwin", "pod", "shell", bash, "--timeout", "60"]
        try:
            proc = await asyncio.to_thread(
                subprocess.run, cmd, capture_output=True, text=True, timeout=90,
            )
        except FileNotFoundError as exc:
            raise _DarwinError(
                503, "`darwin` CLI not found on PATH — install the darwin-cli plugin"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise _DarwinError(504, f"darwin pod shell timed out writing {dest}") from exc
        if proc.returncode != 0:
            tail = (proc.stderr or proc.stdout or "")[-300:].strip()
            raise _DarwinError(
                502,
                f"darwin pod shell failed writing {dest} (exit {proc.returncode}): {tail}",
            )
        with _mtime_guard:
            _mtime_cache[key] = mtime
        mod = _module_for(local, code_dir)
        if mod:
            pushed_modules.append(mod)
    return pushed_modules


async def _exec_reload(modules: list[str], session: str, kernel: str | None) -> None:
    """Refresh the kernel's view of just-written modules. Best-effort.

    Two things have to happen so the next ``from code.X import ...`` sees
    fresh code:

    1. ``importlib.invalidate_caches()`` — Python's path-based finder
       caches per-directory listings the first time it scans them. A
       file we just wrote with ``darwin pod shell`` won't be visible to
       a subsequent import without this call.
    2. If the module was already loaded, ``importlib.reload`` it so
       references to the old code don't linger. On a write that adds a
       new file (module not yet in ``sys.modules``), this step is a
       no-op — invalidate_caches alone is sufficient.

    Parents are processed before children so that, e.g., ``code``
    reloads before ``code.hello``.

    Silent on failure: if the reload exec errors, the next ``from code.X
    import Y`` will still pick up new code thanks to invalidate_caches
    on the next call. Not worth surfacing a non-fatal hiccup.
    """
    if not modules:
        return
    ordered = sorted(set(modules), key=lambda m: (m.count("."), m))
    lines = [
        "import importlib, sys",
        "importlib.invalidate_caches()",
    ]
    for m in ordered:
        lines.append(
            f"if {m!r} in sys.modules:\n"
            f"    try: importlib.reload(sys.modules[{m!r}])\n"
            f"    except Exception: sys.modules.pop({m!r}, None)"
        )
    try:
        await _darwin_exec(
            "\n".join(lines), session=session, kernel=kernel, timeout=60
        )
    except _DarwinError:
        pass


# ── .ipynb read/append ───────────────────────────────────────────────────────

def _empty_notebook() -> dict[str, Any]:
    return {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {
            "kernelspec": {
                "name": "python3",
                "display_name": "Python 3 (Darwin)",
                "language": "python",
            },
            "language_info": {"name": "python"},
        },
        "cells": [],
    }


def _next_exec_count(nb: dict[str, Any]) -> int:
    n = 0
    for cell in nb.get("cells", []):
        if cell.get("cell_type") == "code":
            ec = cell.get("execution_count")
            if isinstance(ec, int) and ec > n:
                n = ec
    return n + 1


def _load_or_empty(target: Path) -> dict[str, Any]:
    if target.is_file():
        try:
            return json.loads(target.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return _empty_notebook()
    return _empty_notebook()


def _atomic_write(target: Path, nb: dict[str, Any]) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = target.with_suffix(target.suffix + ".tmp")
    tmp_path.write_text(json.dumps(nb, indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp_path, target)


def _checkpoint_pending_outputs(
    target: Path,
    run_id: str,
    outputs: list[dict[str, Any]],
    execution_count: int | None,
) -> None:
    """Persist a throttled live-output snapshot without losing cell identity."""
    with _lock_for(target):
        nb = _load_or_empty(target)
        cells = nb.setdefault("cells", [])
        current_idx = _pending_index(cells, 0, run_id)
        if current_idx is None:
            return
        cell = cells[current_idx]
        cell["outputs"] = outputs
        if isinstance(execution_count, int):
            cell["execution_count"] = execution_count
        _atomic_write(target, nb)


def recover_stale_pending(target: Path) -> bool:
    """Turn orphaned running placeholders into durable error cells.

    A process crash clears the in-memory execution registry and stops the
    kernel, but the last atomic checkpoint may still say ``lab_pending``.
    Recover on the next read so the UI never shows an immortal running cell;
    any text/rich output checkpointed before the crash is retained.
    """
    if is_path_pending(target) or not target.is_file():
        return False
    changed = False
    with _lock_for(target):
        # Re-check after acquiring the file lock: a new request may have
        # started while this reader was waiting.
        if is_path_pending(target):
            return False
        nb = _load_or_empty(target)
        for cell in nb.get("cells", []):
            metadata = cell.get("metadata") or {}
            if metadata.get("lab_pending") is not True:
                continue
            finished_at = time.time()
            started_at = metadata.get("lab_started_at")
            metadata["lab_pending"] = False
            metadata["lab_finished_at"] = finished_at
            if isinstance(started_at, (int, float)):
                metadata["lab_duration_ms"] = max(
                    0, round((finished_at - started_at) * 1000)
                )
            metadata.pop("lab_run_id", None)
            outputs = list(cell.get("outputs") or [])
            if (
                len(outputs) == 1
                and outputs[0].get("output_type") == "stream"
                and "Running on" in "".join(outputs[0].get("text") or [])
            ):
                outputs = []
            outputs.append({
                "output_type": "error",
                "ename": "ExecutionLost",
                "evalue": "Lab restarted or lost the kernel before this cell finished.",
                "traceback": [
                    "ExecutionLost: Lab restarted or lost the kernel before this cell finished."
                ],
            })
            cell["outputs"] = outputs
            changed = True
        if changed:
            _atomic_write(target, nb)
    return changed


def _write_pending_cell(
    target: Path, *,
    source: str,
    exec_count: int,
    cell_index: int | None = None,
    insert_at: int | None = None,
    provider_label: str = "kernel",
    provider: str = "darwin",
    actor: str = "agent",
) -> tuple[int, str, str, float] | None:
    """Write a "running" placeholder cell to disk BEFORE shelling out to
    darwin.

    Why: the darwin CLI call is synchronous and can take minutes for a
    Trino query. Without this placeholder the .ipynb file doesn't change
    until darwin returns, so the UI shows no feedback at all during the
    run — the user can't even tell which cell is executing. By writing a
    minimal placeholder first, the file watcher broadcasts the change
    immediately and the open notebook view paints the new cell with the
    ⏳ marker. When darwin returns we replace this same cell with the
    real outputs.

    Mode handling matches ``_write_code_cell`` (append / replace /
    insert). Returns the placeholder's index, or ``None`` if the
    cell_index / insert_at value is out of range (caller surfaces the
    error after dropping the lock).
    """
    nb = _load_or_empty(target)
    if provider == "local":
        metadata = nb.setdefault("metadata", {})
        metadata["kernelspec"] = {
            "name": "python3",
            "display_name": "Python 3 (Lab Project Runtime)",
            "language": "python",
        }
        metadata.setdefault("language_info", {"name": "python"})
    cells = nb.setdefault("cells", [])
    run_id = uuid.uuid4().hex
    cell_id = uuid.uuid4().hex[:12]
    if cell_index is not None and 0 <= cell_index < len(cells):
        # Re-execution modifies the same logical nbformat cell. Keep its id
        # stable while swapping in the running placeholder and final outputs.
        cell_id = str(cells[cell_index].get("id") or cell_id)
    action = "modified" if cell_index is not None else "created"
    started_at = time.time()
    placeholder_output, _ = _running_placeholder_output(provider_label)
    placeholder = {
        "id": cell_id,
        "cell_type": "code",
        "execution_count": exec_count,
        # `lab_pending` lets a future frontend pass paint this cell with
        # a "running" frame; harmless to any nbformat consumer that
        # doesn't know about it.
        "metadata": {
            "lab_pending": True,
            "lab_run_id": run_id,
            "lab_actor": actor,
            "lab_action": action,
            "lab_started_at": started_at,
        },
        "source": source.splitlines(keepends=True) if source else [],
        "outputs": [placeholder_output],
    }
    if cell_index is not None:
        if cell_index < 0 or cell_index >= len(cells):
            return None
        cells[cell_index] = placeholder
        idx = cell_index
    elif insert_at is not None:
        if insert_at < 0 or insert_at > len(cells):
            return None
        cells.insert(insert_at, placeholder)
        idx = insert_at
    else:
        cells.append(placeholder)
        idx = len(cells) - 1
    _atomic_write(target, nb)
    return idx, run_id, cell_id, started_at


def _pending_index(cells: list[dict[str, Any]], idx: int, run_id: str) -> int | None:
    """Find a running placeholder after concurrent inserts may have shifted it."""
    if 0 <= idx < len(cells):
        metadata = cells[idx].get("metadata") or {}
        if metadata.get("lab_run_id") == run_id:
            return idx
    for current, cell in enumerate(cells):
        if (cell.get("metadata") or {}).get("lab_run_id") == run_id:
            return current
    return None


def _mark_pending_failed(
    target: Path, idx: int, run_id: str, ename: str, evalue: str
) -> None:
    """Convert the pending placeholder at ``idx`` into an error cell.

    Called when darwin itself fails (auth expired, pod cold-starting,
    CLI missing) — we'd otherwise leave a ⏳ cell hanging forever. The
    write triggers the watcher again so the UI sees the error promptly.
    """
    nb = _load_or_empty(target)
    cells = nb.get("cells", [])
    current_idx = _pending_index(cells, idx, run_id)
    if current_idx is not None:
        cell = cells[current_idx]
        metadata = cell.setdefault("metadata", {})
        finished_at = time.time()
        started_at = metadata.get("lab_started_at")
        metadata["lab_pending"] = False
        metadata["lab_finished_at"] = finished_at
        if isinstance(started_at, (int, float)):
            metadata["lab_duration_ms"] = max(
                0, round((finished_at - started_at) * 1000)
            )
        metadata.pop("lab_run_id", None)
        outputs = list(cell.get("outputs") or [])
        if (
            len(outputs) == 1
            and outputs[0].get("output_type") == "stream"
            and "Running on" in "".join(outputs[0].get("text") or [])
        ):
            outputs = []
        outputs.append({
            "output_type": "error",
            "ename": ename,
            "evalue": evalue,
            "traceback": [evalue],
        })
        cell["outputs"] = outputs
        _atomic_write(target, nb)


def _write_code_cell(
    target: Path, *,
    source: str,
    cell_outputs: list[dict[str, Any]],
    exec_count: int,
    cell_index: int | None,
    insert_at: int | None = None,
    cell_id: str | None = None,
) -> int:
    """Append, replace, or insert a code cell.

    - ``cell_index`` set → replace the existing cell at that index.
    - ``insert_at`` set  → insert a NEW cell at that index, shifting everything
      from that index onward by one. ``insert_at == len(cells)`` is the same as
      a plain append.
    - neither set        → append at the end.

    ``cell_index`` and ``insert_at`` are mutually exclusive. Returns the final
    index of the cell in the notebook so the caller can correlate the response
    with the on-disk position.
    """
    if cell_index is not None and insert_at is not None:
        raise HTTPException(
            status_code=400,
            detail="cell_index and insert_at are mutually exclusive",
        )
    nb = _load_or_empty(target)
    cells = nb.setdefault("cells", [])
    new_cell = {
        "id": cell_id or uuid.uuid4().hex[:12],
        "cell_type": "code",
        "execution_count": exec_count,
        "metadata": {},
        "source": source.splitlines(keepends=True) if source else [],
        "outputs": cell_outputs or [],
    }
    if cell_index is not None:
        if cell_index < 0 or cell_index >= len(cells):
            raise HTTPException(
                status_code=404,
                detail=f"cell_index {cell_index} out of range (notebook has {len(cells)} cells)",
            )
        cells[cell_index] = new_cell
        idx = cell_index
    elif insert_at is not None:
        if insert_at < 0 or insert_at > len(cells):
            raise HTTPException(
                status_code=404,
                detail=f"insert_at {insert_at} out of range (notebook has {len(cells)} cells; valid is 0..{len(cells)})",
            )
        cells.insert(insert_at, new_cell)
        idx = insert_at
    else:
        cells.append(new_cell)
        idx = len(cells) - 1
    _atomic_write(target, nb)
    return idx


def _replace_pending_cell(
    target: Path,
    *,
    pending_index: int,
    run_id: str,
    source: str,
    cell_outputs: list[dict[str, Any]],
    exec_count: int,
    actor: str,
) -> int:
    """Replace this request's placeholder, resilient to concurrent inserts."""
    nb = _load_or_empty(target)
    cells = nb.setdefault("cells", [])
    current_idx = _pending_index(cells, pending_index, run_id)
    if current_idx is None:
        raise HTTPException(status_code=409, detail="running cell changed before execution completed")
    pending_cell = cells[current_idx]
    pending_metadata = pending_cell.get("metadata") or {}
    cell_id = str(pending_cell.get("id") or uuid.uuid4().hex[:12])
    finished_at = time.time()
    started_at = pending_metadata.get("lab_started_at")
    metadata: dict[str, Any] = {
        "lab_actor": actor,
        "lab_action": pending_metadata.get("lab_action", "created"),
        "lab_finished_at": finished_at,
    }
    if isinstance(started_at, (int, float)):
        metadata["lab_started_at"] = started_at
        metadata["lab_duration_ms"] = max(
            0, round((finished_at - started_at) * 1000)
        )
    cells[current_idx] = {
        "id": cell_id,
        "cell_type": "code",
        "execution_count": exec_count,
        "metadata": metadata,
        "source": source.splitlines(keepends=True) if source else [],
        "outputs": cell_outputs or [],
    }
    _atomic_write(target, nb)
    return current_idx


# ── Request / response schema ────────────────────────────────────────────────

class ExecBody(BaseModel):
    path: str = Field(..., description="Notebook path relative to the monorepo root")
    code: str = Field(..., description="Code to execute on the Darwin kernel")
    kernel: str | None = Field(
        default=None,
        description="Darwin kernel type (python3, pyspark, spark-scala, r, python3-gpu)",
    )
    # No upper bound — long-running analytical queries (multi-stage Trino
    # joins, full-window dashboards) can legitimately need 10+ minutes.
    # Default is 30 minutes so the common case works without explicit override.
    timeout: int = Field(default=1800, ge=1)
    # When None: append a new cell at the end.
    # When set: replace the cell at that index (source + outputs).
    cell_index: int | None = Field(default=None, ge=0)
    # When set: insert a NEW cell at that index, shifting later cells down.
    # ``insert_at == len(cells)`` is identical to an append. Mutually
    # exclusive with ``cell_index``.
    insert_at: int | None = Field(default=None, ge=0)
    cell_id: str | None = Field(
        default=None,
        description="Stable nbformat cell id; preferred over cell_index for replacing a cell",
    )
    actor: Literal["human", "agent"] = Field(
        default="agent",
        description="Origin of the notebook mutation for UI/audit metadata",
    )


class CellDeleteBody(BaseModel):
    path: str = Field(..., description="Notebook path relative to the monorepo root")
    cell_index: int | None = Field(default=None, ge=0)
    cell_id: str | None = None


# ── Routes ───────────────────────────────────────────────────────────────────

@router.get("/api/nb/session")
def session_for(path: str, request: Request) -> dict:
    """Return the provider/session pinned to this notebook path."""
    root = auth.request_root(request)
    _safe_resolve(root, path)  # validate only
    if _configured_local(root, path):
        from core.notebook_kernel import session_name

        return {
            "path": path,
            "session": session_name(root, path),
            "provider": "local",
            "capabilities": ["execute", "restart", "interrupt"],
        }
    return {
        "path": path,
        "session": _session_for(path),
        "provider": "darwin",
        "capabilities": ["execute", "restart"],
    }


@router.get("/api/nb/live")
def live_executions(path: str, request: Request) -> dict[str, Any]:
    """Return replayable in-flight state for reconnecting notebook views."""
    root = auth.request_root(request)
    target = _safe_resolve(root, path)
    workspace = auth.workspace_id_for_root(root) or ""
    snapshots = _live_snapshot(target)
    # A run stays in the registry for a few instructions after its final file
    # replacement while the terminal event is being broadcast. Cross-check the
    # durable run marker so a browser opening in that tiny window cannot overlay
    # an already-finished cell with a stale running snapshot.
    with _lock_for(target):
        pending_run_ids = {
            str((cell.get("metadata") or {}).get("lab_run_id"))
            for cell in _load_or_empty(target).get("cells", [])
            if (cell.get("metadata") or {}).get("lab_pending") is True
        }
    return {
        "path": path,
        "workspace": workspace,
        "executions": [
            snapshot
            for snapshot in snapshots
            if snapshot["run_id"] in pending_run_ids
        ],
    }


@router.post("/api/nb/exec")
async def exec_cell(body: ExecBody, request: Request) -> dict:
    """Execute ``body.code`` in the notebook's pinned kernel.

    Two-phase write so the UI gets live feedback:

      1. Write a ⏳ "running" placeholder cell at the target index. The
         file watcher broadcasts this write, and any open notebook view
         re-renders with the new pending cell within ~100 ms.
      2. Execute in the configured local Jupyter runtime (or legacy Darwin),
         streaming accepted IOPub events over the shared WebSocket.
      3. Replace the placeholder cell with the kernel's final outputs. Same
         watcher broadcast → UI re-renders with the final result.

    If the provider itself fails (runtime broken, auth expired, CLI missing),
    the placeholder is converted in place to an error cell so the user
    isn't left staring at a frozen ⏳.

    Always returns 200 with the new cell on success — even if the cell
    itself raised (Jupyter reports that as an ``error`` output, which
    still belongs in the notebook). The endpoint only 4xx/5xx's when the
    darwin CLI cannot run.
    """
    root = auth.request_root(request)
    target = _safe_resolve(root, body.path)
    workspace = auth.workspace_id_for_root(root) or ""
    local_handle = _required_local_handle(root, body.path) if _configured_local(root, body.path) else None
    if local_handle is not None:
        from core.notebook_kernel import session_name

        session = session_name(root, body.path)
        provider = "local"
    else:
        session = _session_for(body.path)
        provider = "darwin"
    if body.cell_index is not None and body.insert_at is not None:
        raise HTTPException(
            status_code=400,
            detail="cell_index and insert_at are mutually exclusive",
        )
    if body.cell_id is not None and body.insert_at is not None:
        raise HTTPException(
            status_code=400,
            detail="cell_id and insert_at are mutually exclusive",
        )

    replace_index = body.cell_index
    if body.cell_id is not None:
        with _lock_for(target):
            cells = _load_or_empty(target).get("cells", [])
            matches = [i for i, cell in enumerate(cells) if cell.get("id") == body.cell_id]
        if not matches:
            raise HTTPException(status_code=404, detail=f"cell_id {body.cell_id!r} not found")
        replace_index = matches[0]

    # Phase 1: write the pending placeholder so the UI sees a running
    # cell immediately. Pick the exec_count now so the placeholder shows
    # the right [n] gutter; we'll overwrite later with Darwin's actual
    # count if it differs.
    provider_label = "project kernel" if provider == "local" else "Darwin"
    # Count in-flight requests rather than keeping a boolean: queued cells in
    # the same notebook must keep the path marked active when an earlier cell
    # completes.
    _mark_running(target)
    try:
        with _lock_for(target):
            pre_exec_count = _next_exec_count(_load_or_empty(target))
            pending_result = _write_pending_cell(
                target,
                source=body.code,
                exec_count=pre_exec_count,
                cell_index=replace_index,
                insert_at=body.insert_at,
                provider_label=provider_label,
                provider=provider,
                actor=body.actor,
            )
    except BaseException:
        _mark_done(target)
        raise
    if pending_result is None:
        # cell_index/insert_at was out of range — surface a 404 the same
        # way the post-darwin path would. Doing this AFTER releasing the
        # lock avoids HTTPException unwinding through the lock.
        nb = _load_or_empty(target)
        cells = nb.get("cells", [])
        if replace_index is not None:
            detail = (
                f"cell_index {replace_index} out of range "
                f"(notebook has {len(cells)} cells)"
            )
        else:
            detail = (
                f"insert_at {body.insert_at} out of range "
                f"(notebook has {len(cells)} cells; valid is 0..{len(cells)})"
            )
        _mark_done(target)
        raise HTTPException(status_code=404, detail=detail)
    pending_idx, run_id, cell_id, started_at = pending_result
    live_started = _live_start(
        target,
        path=body.path,
        workspace=workspace,
        run_id=run_id,
        cell_id=cell_id,
        cell_index=pending_idx,
        actor=body.actor,
        source=body.code,
        provider=provider,
        provider_label=provider_label,
        execution_count=pre_exec_count,
        started_at=started_at,
    )
    await _publish_notebook_event(request, {"phase": "started", **live_started})

    # Phase 2: run darwin (slow). If it errors, mark the placeholder as
    # failed so the UI shows the error instead of a stuck ⏳ cell.
    # Mark this path as "currently running" so the sidebar can show the
    # green pulse dot. Cleared in every exit path below.
    async def on_kernel_event(kernel_event: dict[str, Any]) -> None:
        payload, checkpoint, checkpoint_count = _live_apply_kernel_event(
            target, run_id, kernel_event
        )
        if checkpoint is not None:
            await asyncio.to_thread(
                _checkpoint_pending_outputs,
                target,
                run_id,
                checkpoint,
                checkpoint_count,
            )
        if payload is not None:
            await _publish_notebook_event(request, payload)

    async def publish_terminal(phase: str, detail: str | None = None) -> None:
        cells = parse_notebook(str(target))
        cell = next((candidate for candidate in cells if candidate.get("id") == cell_id), None)
        payload: dict[str, Any] = {
            "phase": phase,
            "path": body.path,
            "workspace": workspace,
            "run_id": run_id,
            "cell_id": cell_id,
            "cell_index": next(
                (index for index, candidate in enumerate(cells) if candidate.get("id") == cell_id),
                pending_idx,
            ),
            "actor": body.actor,
            "provider": provider,
            "cell": cell,
        }
        if detail:
            payload["detail"] = detail
        await _publish_notebook_event(request, payload)

    try:
        if local_handle is not None:
            from core.notebook_kernel import execute as execute_local

            result = await execute_local(
                root,
                body.path,
                local_handle,
                body.code,
                body.timeout,
                on_event=on_kernel_event,
            )
        else:
            # Darwin-only compatibility bootstrap. Local runtimes expose
            # project libraries directly through their configured Python/PATH.
            if _code_dir(root).is_dir():
                if _bootstrap_needed(session):
                    try:
                        await _exec_bootstrap(session, body.kernel)
                    except _DarwinError:
                        _bootstrap_unmark(session)
                        raise
                pushed_modules = await _push_code(root)
                if pushed_modules:
                    await _exec_reload(pushed_modules, session, body.kernel)

            result = await _darwin_exec(
                body.code, session=session, kernel=body.kernel, timeout=body.timeout
            )
    except _DarwinError as exc:
        with _lock_for(target):
            _mark_pending_failed(
                target, pending_idx, run_id, type(exc).__name__, exc.detail
            )
        await publish_terminal("failed", exc.detail)
        _live_remove(target, run_id)
        _mark_done(target)
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except Exception as exc:
        from core.notebook_kernel import KernelExecutionError

        if isinstance(exc, KernelExecutionError):
            with _lock_for(target):
                _mark_pending_failed(
                    target, pending_idx, run_id, type(exc).__name__, exc.detail
                )
            await publish_terminal("failed", exc.detail)
            _live_remove(target, run_id)
            _mark_done(target)
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
        with _lock_for(target):
            _mark_pending_failed(
                target, pending_idx, run_id, type(exc).__name__, str(exc)
            )
        await publish_terminal("failed", str(exc))
        _live_remove(target, run_id)
        _mark_done(target)
        raise
    except BaseException as exc:
        with _lock_for(target):
            _mark_pending_failed(
                target,
                pending_idx,
                run_id,
                type(exc).__name__,
                str(exc) or "execution cancelled",
            )
        # Cancellation may already have cancelled this task; shield the final
        # notification so other open notebook views are not left running.
        try:
            await asyncio.shield(publish_terminal("failed", str(exc) or "execution cancelled"))
        except Exception:
            pass
        _live_remove(target, run_id)
        _mark_done(target)
        raise

    cell_outputs = result.get("cell_outputs") or []
    kernel_id = result.get("kernel_id")
    exec_count_from_kernel = result.get("execution_count")

    # Phase 3: replace the placeholder with the real outputs. We use
    # cell_index=pending_idx so the placeholder is overwritten in place
    # — no shifting, no duplicate cells.
    try:
        with _lock_for(target):
            if isinstance(exec_count_from_kernel, int) and exec_count_from_kernel > 0:
                exec_count = exec_count_from_kernel
            else:
                exec_count = pre_exec_count

            idx = _replace_pending_cell(
                target,
                pending_index=pending_idx,
                run_id=run_id,
                source=body.code,
                cell_outputs=cell_outputs,
                exec_count=exec_count,
                actor=body.actor,
            )

            # Re-parse via the same helper the GET endpoint uses so the cell we
            # return matches the shape the UI already renders.
            cells = parse_notebook(str(target))
    except BaseException as exc:
        # Final persistence is a failure boundary too (for example, an
        # external editor removed the running cell). Always terminate the live
        # run and turn any surviving placeholder into an error.
        try:
            with _lock_for(target):
                _mark_pending_failed(
                    target,
                    pending_idx,
                    run_id,
                    type(exc).__name__,
                    str(exc) or "failed to persist completed cell",
                )
            await asyncio.shield(
                publish_terminal(
                    "failed", str(exc) or "failed to persist completed cell"
                )
            )
        finally:
            _live_remove(target, run_id)
        raise
    finally:
        _mark_done(target)

    terminal_phase = "finished"
    if any(
        output.get("output_type") == "error"
        and output.get("ename") == "KeyboardInterrupt"
        for output in cell_outputs
    ):
        terminal_phase = "interrupted"
    try:
        await publish_terminal(terminal_phase)
    finally:
        _live_remove(target, run_id)

    return {
        "path": body.path,
        "workspace": workspace,
        "session": session,
        "provider": provider,
        "kernel_id": kernel_id,
        "execution_count": exec_count,
        "cell_index": idx,
        "cell": cells[idx] if 0 <= idx < len(cells) else None,
        "mtime": target.stat().st_mtime,
    }


class SessionRestartBody(BaseModel):
    path: str = Field(..., description="Notebook path relative to the monorepo root")


@router.post("/api/nb/session/restart")
async def session_restart(body: SessionRestartBody, request: Request) -> dict:
    """Restart the local or Darwin kernel pinned to ``body.path``."""
    root = auth.request_root(request)
    _safe_resolve(root, body.path)  # validate
    if _configured_local(root, body.path):
        handle = _required_local_handle(root, body.path)
        from core.notebook_kernel import restart as restart_local, session_name

        try:
            was_running = await restart_local(root, body.path, handle)
        except Exception as exc:
            from core.notebook_kernel import KernelExecutionError

            if isinstance(exc, KernelExecutionError):
                raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
            raise
        return {
            "path": body.path,
            "session": session_name(root, body.path),
            "provider": "local",
            "restarted": was_running,
        }

    session = _session_for(body.path)
    try:
        proc = await asyncio.to_thread(
            subprocess.run,
            ["darwin", "kernel", "restart", "--session", session],
            capture_output=True, text=True, timeout=60,
        )
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=503,
            detail="`darwin` CLI not found on PATH — install the darwin-cli plugin",
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=504, detail=f"darwin timed out after {exc.timeout}s") from exc

    if proc.returncode == 0:
        return {"path": body.path, "session": session, "restarted": True}

    err_tail = (proc.stderr or proc.stdout or "")[-500:]
    if proc.returncode == 2:
        raise HTTPException(status_code=401, detail="darwin auth expired — run `darwin auth setup`")
    # Some pods report "no kernel running" with a non-zero exit but that's
    # actually a no-op success for us — clearing what's already clear.
    if "no kernel" in err_tail.lower() or "not found" in err_tail.lower():
        return {"path": body.path, "session": session, "restarted": False, "note": "no running kernel — next run will start a fresh one"}
    raise HTTPException(
        status_code=500,
        detail=f"darwin kernel restart failed (exit {proc.returncode}): {err_tail.strip()}",
    )


@router.post("/api/nb/session/interrupt")
async def session_interrupt(body: SessionRestartBody, request: Request) -> dict:
    """Interrupt a currently running host-local notebook cell."""
    root = auth.request_root(request)
    _safe_resolve(root, body.path)
    if not _configured_local(root, body.path):
        raise HTTPException(status_code=400, detail="interrupt is currently available for local runtimes")
    handle = _required_local_handle(root, body.path)
    from core.notebook_kernel import interrupt as interrupt_local, session_name

    interrupted = await interrupt_local(root, body.path, handle)
    return {
        "path": body.path,
        "session": session_name(root, body.path),
        "provider": "local",
        "interrupted": interrupted,
    }


@router.post("/api/nb/cell/delete")
def delete_cell(body: CellDeleteBody, request: Request) -> dict:
    """Remove a cell by stable id (preferred) or legacy positional index."""
    root = auth.request_root(request)
    target = _safe_resolve(root, body.path)
    if not target.is_file():
        raise HTTPException(status_code=404, detail="notebook not found")

    with _lock_for(target):
        nb = _load_or_empty(target)
        cells = nb.setdefault("cells", [])
        cell_index = body.cell_index
        if body.cell_id is not None:
            cell_index = next(
                (i for i, cell in enumerate(cells) if cell.get("id") == body.cell_id),
                None,
            )
        if cell_index is None:
            detail = "cell_id not found" if body.cell_id else "cell_id or cell_index is required"
            raise HTTPException(status_code=404 if body.cell_id else 400, detail=detail)
        if cell_index < 0 or cell_index >= len(cells):
            raise HTTPException(
                status_code=404,
                detail=f"cell_index {cell_index} out of range (notebook has {len(cells)} cells)",
            )
        del cells[cell_index]
        _atomic_write(target, nb)

    return {
        "path": body.path,
        "remaining_cells": len(cells),
        "mtime": target.stat().st_mtime,
    }
