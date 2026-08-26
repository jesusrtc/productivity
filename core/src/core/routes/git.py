"""Framework Git controls and content push endpoints.

Two endpoints power the dashboard's framework push / content sync
buttons. The Makefile is the single source of truth for what each button
does; this module just shells out via `make <target>` and surfaces
stdout/stderr to the UI.

The top-bar update control is deliberately different: it pulls ``origin/main``
in the framework checkout, then replaces the running Python process with a
fresh ``python -m core`` process. Replacing the process in-place avoids the
port ownership race that a child ``make restart`` can hit while its parent is
still serving the request.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from lab import paths

from core import auth


router = APIRouter()
log = logging.getLogger(__name__)


_TIMEOUT_S = 30
_GIT_UPDATE_TIMEOUT_S = 120
_BOOT_ID = uuid.uuid4().hex
_RESTART_LOCK = threading.Lock()
_RESTART_SCHEDULED = False


def _run_make(root: Path, target: str) -> dict:
    try:
        proc = subprocess.run(
            ["make", target],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail=f"make {target} timed out after {_TIMEOUT_S}s")
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    if proc.returncode != 0:
        # 409 because the working tree state is the most common cause
        # (dirty, nothing to push). Concatenate stderr + stdout so the toast
        # shows whatever make reported.
        message = err or out or "push failed"
        if out and err and out != err:
            message = f"{err}\n{out}"
        raise HTTPException(status_code=409, detail=message)
    return {"status": "ok", "message": out}


def _run_git(root: Path, args: list[str], *, timeout: int = _TIMEOUT_S) -> str:
    command = ["git", "-C", str(root), *args]
    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        label = " ".join(args)
        raise HTTPException(
            status_code=504,
            detail=f"git {label} timed out after {timeout}s",
        ) from exc
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    if proc.returncode != 0:
        message = err or out or f"git {' '.join(args)} failed"
        if out and err and out != err:
            message = f"{err}\n{out}"
        raise HTTPException(status_code=409, detail=message)
    return out or err


def _exec_current_process(root: Path) -> None:
    """Replace this server in-place so no second process races for its port."""
    os.chdir(root)
    os.execv(sys.executable, [sys.executable, "-m", "core"])


def _restart_after_response(root: Path) -> None:
    global _RESTART_SCHEDULED
    # Give Starlette enough time to flush the accepted response before the
    # process disappears. The browser then verifies a new boot id before it
    # reloads the page.
    time.sleep(1.0)
    try:
        _exec_current_process(root)
    except Exception:
        with _RESTART_LOCK:
            _RESTART_SCHEDULED = False
        log.exception("framework update succeeded but process exec restart failed")


def _schedule_exec_restart(root: Path) -> None:
    threading.Thread(
        target=_restart_after_response,
        args=(root,),
        name="lab-update-restart",
        daemon=True,
    ).start()


@router.post("/api/git/push-productivity")
def push_productivity(request: Request) -> dict:
    """Push the Lab framework repo. Errors if the working tree is dirty."""
    root = paths.find_framework_root()
    return _run_make(root, "push-productivity")


@router.post("/api/git/sync-content")
def sync_content(request: Request) -> dict:
    """Stage, commit (if needed), and push the content repo."""
    root = request.app.state.index_cache.root
    return _run_make(root, "push-content")


@router.get("/api/git/runtime")
def git_runtime(request: Request) -> dict:
    """Identity used by the browser to prove that a new server booted."""
    auth.require_admin(request)
    return {"boot_id": _BOOT_ID, "pid": os.getpid()}


@router.post("/api/git/update-restart")
def update_restart(request: Request) -> dict:
    """Pull ``origin/main`` with rebase/autostash, then exec a fresh server."""
    global _RESTART_SCHEDULED
    auth.require_admin(request)
    root = paths.find_framework_root()

    with _RESTART_LOCK:
        if _RESTART_SCHEDULED:
            raise HTTPException(status_code=409, detail="an update/restart is already in progress")
        _RESTART_SCHEDULED = True

    try:
        branch = _run_git(root, ["rev-parse", "--abbrev-ref", "HEAD"])
        if branch != "main":
            raise HTTPException(
                status_code=409,
                detail=f"framework checkout is on {branch!r}; switch it to 'main' before updating",
            )
        message = _run_git(
            root,
            ["pull", "--rebase", "--autostash", "origin", "main"],
            timeout=_GIT_UPDATE_TIMEOUT_S,
        )
        revision = _run_git(root, ["rev-parse", "--short", "HEAD"])
        _schedule_exec_restart(root)
    except Exception:
        with _RESTART_LOCK:
            _RESTART_SCHEDULED = False
        raise

    return {
        "status": "restarting",
        "message": message,
        "revision": revision,
        "boot_id": _BOOT_ID,
    }
