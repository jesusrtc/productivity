"""Git push endpoints — invoke the Makefile push targets.

Two endpoints power the dashboard's framework push / content sync
buttons. The Makefile is the single source of truth for what each button
does; this module just shells out via `make <target>` and surfaces
stdout/stderr to the UI.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from lab import paths


router = APIRouter()


_TIMEOUT_S = 30


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
