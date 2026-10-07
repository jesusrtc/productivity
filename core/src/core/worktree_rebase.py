"""Explicit worktree updates from origin/master, without switching or pushing."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import threading

from fastapi import HTTPException


_LOCK = threading.Lock()
_ACTIVE: set[Path] = set()
_TARGET = "origin/master"


def _git(root: Path, args: list[str], *, timeout: int = 10) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            ["git", "-C", str(root), "-c", "credential.interactive=false", *args],
            capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "Never",
                 "GIT_EDITOR": "true", "GIT_SEQUENCE_EDITOR": "true"},
        )
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=504, detail=f"Git {args[0]} timed out. Check this worktree before retrying.") from exc
    except OSError as exc:
        raise HTTPException(status_code=409, detail=f"Could not run Git: {exc}") from exc


def _output(proc: subprocess.CompletedProcess) -> str:
    return "\n".join(part.strip() for part in (proc.stdout, proc.stderr) if part and part.strip())


def _value(root: Path, args: list[str]) -> str:
    proc = _git(root, args)
    if proc.returncode:
        raise HTTPException(status_code=409, detail=_output(proc) or "Could not read the worktree's Git state.")
    return proc.stdout.strip()


def _branch(root: Path) -> str:
    proc = _git(root, ["symbolic-ref", "--quiet", "--short", "HEAD"])
    if proc.returncode:
        raise HTTPException(status_code=409, detail="This worktree has detached HEAD. Switch to its branch before rebasing.")
    return proc.stdout.strip()


def _rebase_paused(git_dir: Path) -> bool:
    return any((git_dir / name).exists() for name in ("rebase-merge", "rebase-apply"))


def _ready(root: Path, git_dir: Path) -> None:
    if _rebase_paused(git_dir):
        raise HTTPException(status_code=409, detail="A rebase is already paused in this worktree. Resolve it with git rebase --continue or git rebase --abort first.")
    if any((git_dir / name).exists() for name in ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD")):
        raise HTTPException(status_code=409, detail="Finish or abort the current Git operation in this worktree before rebasing.")
    if _value(root, ["diff", "--name-only", "--diff-filter=U", "-z"]):
        raise HTTPException(status_code=409, detail="This worktree has unresolved file conflicts. Resolve them before rebasing.")


def pull_rebase_master(root: Path) -> dict:
    """The caller must authorize the exact Git checkout root before mutation."""
    git_dir = Path(_value(root, ["rev-parse", "--absolute-git-dir"])).resolve()
    common_dir = (root / _value(root, ["rev-parse", "--git-common-dir"])).resolve()
    if git_dir == common_dir:
        raise HTTPException(status_code=409, detail="This action is for linked worktrees. Select a worktree checkout first.")

    # Linked checkouts share refs and FETCH_HEAD. Prevent duplicate or overlapping
    # updates across browsers and sibling worktrees, without retaining idle locks.
    with _LOCK:
        if common_dir in _ACTIVE:
            raise HTTPException(status_code=409, detail="A worktree update is already running for this repository.")
        _ACTIVE.add(common_dir)
    try:
        _ready(root, git_dir)
        branch = _branch(root)
        fetched = _git(root, ["fetch", "--no-tags", "origin",
                              "+refs/heads/master:refs/remotes/origin/master"], timeout=120)
        if fetched.returncode:
            raise HTTPException(status_code=409, detail=_output(fetched) or "Could not fetch origin/master. The worktree was not rebased.")
        revision = _value(root, ["rev-parse", "refs/remotes/origin/master^{commit}"])
        _ready(root, git_dir)
        if _branch(root) != branch:
            raise HTTPException(status_code=409, detail="The worktree's branch changed while fetching. Retry from the intended branch.")
        rebased = _git(root, ["rebase", "--autostash", "--no-update-refs", revision], timeout=120)
        paused = _rebase_paused(git_dir)
        conflicts = _git(root, ["diff", "--name-only", "--diff-filter=U", "-z"])
        if conflicts.returncode:
            raise HTTPException(status_code=409, detail="Git finished, but its conflict state could not be checked. Inspect this worktree before retrying.")
        files = [name for name in conflicts.stdout.split("\0") if name]
        status = "conflict" if paused else "local_changes_conflict" if files else "error" if rebased.returncode else "ok"
        message = {
            "ok": f"{branch} rebased onto origin/master.",
            "conflict": "Rebase paused on conflicts. Resolve them in this worktree, then continue or abort.",
            "local_changes_conflict": "Rebase finished, but restoring local edits left conflicts. Resolve those files; the autostash is retained by Git.",
            "error": "Git could not complete the rebase. Inspect the output before retrying.",
        }[status]
        return {"status": status, "message": message, "output": "\n\n".join(filter(None, (_output(fetched), _output(rebased)))),
                "path": str(root), "branch": branch, "target": _TARGET, "revision": revision,
                "rebase_paused": paused, "conflicted_files": files}
    finally:
        with _LOCK:
            _ACTIVE.discard(common_dir)
