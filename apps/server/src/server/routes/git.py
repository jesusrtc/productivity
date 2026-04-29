"""Git push endpoints — thin wrappers over scripts/push.sh.

Two endpoints power the dashboard's "Push productivity" / "Sync content"
buttons. The shell script (scripts/push.sh) is the source of truth for
what each button does; this module just shells out and returns the
captured stdout/stderr to the UI.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request


router = APIRouter()


_TIMEOUT_S = 30


def _push_script_path(root: Path) -> Path:
    return root / "scripts" / "push.sh"


def _run_push(root: Path, target: str) -> dict:
    script = _push_script_path(root)
    if not script.is_file():
        raise HTTPException(status_code=500, detail=f"push script missing: {script}")
    try:
        proc = subprocess.run(
            [str(script), target],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail=f"push timed out after {_TIMEOUT_S}s")
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    if proc.returncode != 0:
        # 409 because the working tree state is the most common cause
        # (dirty, nothing to push). Concatenate stderr + stdout so the toast
        # shows whatever the script reported.
        message = err or out or "push failed"
        if out and err and out != err:
            message = f"{err}\n{out}"
        raise HTTPException(status_code=409, detail=message)
    return {"status": "ok", "message": out}


@router.post("/api/git/push-productivity")
async def push_productivity(request: Request) -> dict:
    """Push the productivity monorepo. Errors if the working tree is dirty."""
    root = request.app.state.index_cache.root
    return _run_push(root, "productivity")


@router.post("/api/git/sync-content")
async def sync_content(request: Request) -> dict:
    """Stage, commit (if needed), and push the content repo."""
    root = request.app.state.index_cache.root
    return _run_push(root, "content")
