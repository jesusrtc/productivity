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
import hashlib
import json
import os
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from server.diff_parser import parse_notebook


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
    timeout: int = Field(default=600, ge=1, le=3600)
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
async def session_for(path: str, request: Request) -> dict:
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
    try:
        result = await _darwin_exec(
            body.code, session=session, kernel=body.kernel, timeout=body.timeout
        )
    except _DarwinError as exc:
        with _lock_for(target):
            _mark_pending_failed(target, pending_idx, type(exc).__name__, exc.detail)
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    cell_outputs = result.get("cell_outputs") or []
    kernel_id = result.get("kernel_id")
    exec_count_from_darwin = result.get("execution_count")

    # Phase 3: replace the placeholder with the real outputs. We use
    # cell_index=pending_idx so the placeholder is overwritten in place
    # — no shifting, no duplicate cells.
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
async def delete_cell(body: CellDeleteBody, request: Request) -> dict:
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
