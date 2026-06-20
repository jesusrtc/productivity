"""Execute code on Darwin via `darwin code execute` and append the result to a
local ``.ipynb`` notebook.

This is the single write path the UI **and** Claude Code both use:

    POST /api/nb/exec   { "path": "...rel.ipynb", "code": "...", "kernel": "python3" }

The endpoint:

1. Validates ``path`` (must live under the monorepo, must end in ``.ipynb``).
2. Derives a stable Darwin session name from the path so every cell appended to
   the same file lands on the same remote kernel.
3. Shells out to the ``darwin`` CLI, capturing its JSON envelope on stdout.
4. Loads (or creates) the ``.ipynb`` on disk, appends a new code cell with the
   exact ``cell_outputs`` Darwin returned (they're already nbformat-shaped),
   bumps ``execution_count``, and saves.
5. Returns the new cell in the same shape ``GET /api/nb`` already uses, plus the
   session id.

Because the file lives under ``content/`` and the watcher rebroadcasts every
write as an ``index-updated`` WS event, **any open notebook view re-renders
automatically** — whether the run came from the UI or from Claude Code calling
the endpoint over curl.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import shlex
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from core.diff_parser import parse_notebook


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


# ── Per-path write lock ──────────────────────────────────────────────────────
# Two concurrent execs to the same file would race on the JSON read-modify-
# write. The lock is held only across the local file mutation, not across the
# Darwin call (Darwin handles its own kernel-level serialization via --session).

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

_pending_paths: set[str] = set()
_pending_guard = threading.Lock()


def _mark_running(target: Path) -> None:
    with _pending_guard:
        _pending_paths.add(str(target.resolve()))


def _mark_done(target: Path) -> None:
    with _pending_guard:
        _pending_paths.discard(str(target.resolve()))


def is_path_pending(target: Path) -> bool:
    with _pending_guard:
        return str(target.resolve()) in _pending_paths


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


def _write_pending_cell(
    target: Path, *,
    source: str,
    exec_count: int,
    cell_index: int | None = None,
    insert_at: int | None = None,
) -> int | None:
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
    cells = nb.setdefault("cells", [])
    placeholder = {
        "cell_type": "code",
        "execution_count": exec_count,
        # `lab_pending` lets a future frontend pass paint this cell with
        # a "running" frame; harmless to any nbformat consumer that
        # doesn't know about it.
        "metadata": {"lab_pending": True},
        "source": source.splitlines(keepends=True) if source else [],
        "outputs": [{
            "output_type": "stream",
            "name": "stdout",
            "text": ["⏳ Running on Darwin…\n"],
        }],
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
    return idx


def _mark_pending_failed(target: Path, idx: int, ename: str, evalue: str) -> None:
    """Convert the pending placeholder at ``idx`` into an error cell.

    Called when darwin itself fails (auth expired, pod cold-starting,
    CLI missing) — we'd otherwise leave a ⏳ cell hanging forever. The
    write triggers the watcher again so the UI sees the error promptly.
    """
    nb = _load_or_empty(target)
    cells = nb.get("cells", [])
    if 0 <= idx < len(cells):
        cells[idx]["metadata"]["lab_pending"] = False
        cells[idx]["outputs"] = [{
            "output_type": "error",
            "ename": ename,
            "evalue": evalue,
            "traceback": [evalue],
        }]
        _atomic_write(target, nb)


def _write_code_cell(
    target: Path, *,
    source: str,
    cell_outputs: list[dict[str, Any]],
    exec_count: int,
    cell_index: int | None,
    insert_at: int | None = None,
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


class CellDeleteBody(BaseModel):
    path: str = Field(..., description="Notebook path relative to the monorepo root")
    cell_index: int = Field(..., ge=0)


# ── Routes ───────────────────────────────────────────────────────────────────

@router.get("/api/nb/session")
def session_for(path: str, request: Request) -> dict:
    """Return the Darwin session name pinned to ``path``.

    Lets the UI show which kernel a notebook is using before the first run.
    """
    root: Path = request.app.state.index_cache.root
    _safe_resolve(root, path)  # validate only
    return {"path": path, "session": _session_for(path)}


@router.post("/api/nb/exec")
async def exec_cell(body: ExecBody, request: Request) -> dict:
    """Execute ``body.code`` on Darwin and append the result to ``body.path``.

    Two-phase write so the UI gets live feedback:

      1. Write a ⏳ "running" placeholder cell at the target index. The
         file watcher broadcasts this write, and any open notebook view
         re-renders with the new pending cell within ~100 ms.
      2. Shell out to ``darwin code execute`` (the slow part — can be
         seconds for Python, minutes for Trino).
      3. Replace the placeholder cell with darwin's real outputs. Same
         watcher broadcast → UI re-renders with the final result.

    If darwin itself fails (auth expired, pod cold-start, CLI missing),
    the placeholder is converted in place to an error cell so the user
    isn't left staring at a frozen ⏳.

    Always returns 200 with the new cell on success — even if the cell
    itself raised (Darwin reports that as an ``error`` output, which
    still belongs in the notebook). The endpoint only 4xx/5xx's when the
    darwin CLI cannot run.
    """
    root: Path = request.app.state.index_cache.root
    target = _safe_resolve(root, body.path)
    session = _session_for(body.path)
    if body.cell_index is not None and body.insert_at is not None:
        raise HTTPException(
            status_code=400,
            detail="cell_index and insert_at are mutually exclusive",
        )

    # Phase 1: write the pending placeholder so the UI sees a running
    # cell immediately. Pick the exec_count now so the placeholder shows
    # the right [n] gutter; we'll overwrite later with Darwin's actual
    # count if it differs.
    with _lock_for(target):
        pre_exec_count = _next_exec_count(_load_or_empty(target))
        pending_idx = _write_pending_cell(
            target,
            source=body.code,
            exec_count=pre_exec_count,
            cell_index=body.cell_index,
            insert_at=body.insert_at,
        )
    if pending_idx is None:
        # cell_index/insert_at was out of range — surface a 404 the same
        # way the post-darwin path would. Doing this AFTER releasing the
        # lock avoids HTTPException unwinding through the lock.
        nb = _load_or_empty(target)
        cells = nb.get("cells", [])
        if body.cell_index is not None:
            detail = (
                f"cell_index {body.cell_index} out of range "
                f"(notebook has {len(cells)} cells)"
            )
        else:
            detail = (
                f"insert_at {body.insert_at} out of range "
                f"(notebook has {len(cells)} cells; valid is 0..{len(cells)})"
            )
        raise HTTPException(status_code=404, detail=detail)

    # Phase 2: run darwin (slow). If it errors, mark the placeholder as
    # failed so the UI shows the error instead of a stuck ⏳ cell.
    # Mark this path as "currently running" so the sidebar can show the
    # green pulse dot. Cleared in every exit path below.
    _mark_running(target)
    try:
        # Phase 2a: per-session bootstrap + per-call code sync. Skipped
        # entirely when content/code/ doesn't exist, so the existing
        # exec path is byte-identical for projects that don't use this
        # feature.
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
            _mark_pending_failed(target, pending_idx, type(exc).__name__, exc.detail)
        _mark_done(target)
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except BaseException:
        _mark_done(target)
        raise

    cell_outputs = result.get("cell_outputs") or []
    kernel_id = result.get("kernel_id")
    exec_count_from_darwin = result.get("execution_count")

    # Phase 3: replace the placeholder with the real outputs. We use
    # cell_index=pending_idx so the placeholder is overwritten in place
    # — no shifting, no duplicate cells.
    try:
        with _lock_for(target):
            if isinstance(exec_count_from_darwin, int) and exec_count_from_darwin > 0:
                exec_count = exec_count_from_darwin
            else:
                exec_count = pre_exec_count

            idx = _write_code_cell(
                target,
                source=body.code,
                cell_outputs=cell_outputs,
                exec_count=exec_count,
                cell_index=pending_idx,
            )

            # Re-parse via the same helper the GET endpoint uses so the cell we
            # return matches the shape the UI already renders.
            cells = parse_notebook(str(target))
    finally:
        _mark_done(target)

    return {
        "path": body.path,
        "session": session,
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
    """Restart the Darwin kernel pinned to ``body.path``.

    Kills the running kernel for this notebook's session and lets the next
    ``/api/nb/exec`` call spin up a fresh one. Variables are wiped — same
    semantics as Jupyter's "Restart Kernel".
    """
    root: Path = request.app.state.index_cache.root
    _safe_resolve(root, body.path)  # validate
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


@router.post("/api/nb/cell/delete")
def delete_cell(body: CellDeleteBody, request: Request) -> dict:
    """Remove the cell at ``body.cell_index`` from ``body.path``."""
    root: Path = request.app.state.index_cache.root
    target = _safe_resolve(root, body.path)
    if not target.is_file():
        raise HTTPException(status_code=404, detail="notebook not found")

    with _lock_for(target):
        nb = _load_or_empty(target)
        cells = nb.setdefault("cells", [])
        if body.cell_index < 0 or body.cell_index >= len(cells):
            raise HTTPException(
                status_code=404,
                detail=f"cell_index {body.cell_index} out of range (notebook has {len(cells)} cells)",
            )
        del cells[body.cell_index]
        _atomic_write(target, nb)

    return {
        "path": body.path,
        "remaining_cells": len(cells),
        "mtime": target.stat().st_mtime,
    }
