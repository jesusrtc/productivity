"""Code Search tab — backend.

Scopes git/grep operations to the repos under `<monorepo>/repositories/`
so the lab UI's "Code Search" tab can:

  * list available repos with a cheap summary (branch + last commit),
  * compute richer stats (commits / contributors / files) on demand,
  * search filenames (`git ls-files | grep`) or code (`rg`, falling
    back to `git grep`),
  * read file content,
  * fetch git log for a whole file or a specific line range
    (`git log -L <start>,<end>:<path>`),
  * fetch a single commit's metadata + diff (optionally scoped to one
    file).

All endpoints reject path traversal and repos that aren't real git
checkouts. Searches and git calls have timeouts so a busted repo can't
hang a worker indefinitely.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request


router = APIRouter()


# ─── helpers ────────────────────────────────────────────────────────────


def _repos_root(request: Request) -> Path:
    """Resolve the `repositories/` folder under the monorepo root.

    Returns the path even if it doesn't exist yet — callers handle the
    missing-folder case (empty repo list).
    """
    return request.app.state.index_cache.root / "repositories"


_REPO_NAME_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]*$")
_SHA_RE = re.compile(r"^[0-9a-fA-F]{4,40}$")


def _validate_repo(root: Path, repo: str) -> Path:
    """Map `<repo>` to a real, in-bounds directory or raise 400/404."""
    if not _REPO_NAME_RE.match(repo or ""):
        raise HTTPException(status_code=400, detail="invalid repo name")
    root_r = root.resolve()
    target = (root / repo).resolve()
    # The target must live directly under root, no traversal.
    if target.parent != root_r:
        raise HTTPException(status_code=400, detail="repo escapes repositories/")
    if not target.is_dir():
        raise HTTPException(status_code=404, detail=f"repo {repo!r} not found")
    return target


def _resolve_in_repo(repo_dir: Path, relpath: str) -> Path:
    """Resolve a repo-relative path to an absolute file path.

    Rejects absolute paths and any traversal that lands outside the
    repo. Returns the resolved Path (may not exist — callers check).
    """
    if not relpath or relpath.startswith("/") or ".." in Path(relpath).parts:
        raise HTTPException(status_code=400, detail="invalid path")
    root_r = repo_dir.resolve()
    target = (repo_dir / relpath).resolve()
    if root_r != target and root_r not in target.parents:
        raise HTTPException(status_code=400, detail="path escapes repo")
    return target


def _git(
    cwd: Path,
    args: list[str],
    timeout: float = 5.0,
) -> tuple[int, str, str]:
    """Run `git <args>` inside `cwd` with a timeout.

    Returns (returncode, stdout, stderr). Never raises — timeouts and
    missing-git both surface as a non-zero returncode + empty stdout.
    """
    try:
        proc = subprocess.run(
            ["git", "-C", str(cwd), *args],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        return 124, "", f"git timed out after {timeout}s"
    except FileNotFoundError:
        return 127, "", "git executable not found"


def _git_out(cwd: Path, args: list[str], timeout: float = 5.0) -> str:
    """Convenience: stdout-only, stripped, empty on failure."""
    rc, out, _ = _git(cwd, args, timeout=timeout)
    return out.strip() if rc == 0 else ""


def _is_git_repo(path: Path) -> bool:
    """True if `path/.git` exists (regular dir OR a worktree pointer)."""
    git = path / ".git"
    return git.is_dir() or git.is_file()


# ─── endpoints ──────────────────────────────────────────────────────────


@router.get("/api/code-search/repos")
async def list_repos(request: Request) -> list[dict]:
    """List git repos under `repositories/` with a cheap per-repo summary.

    Heavy stats (commit count, contributor count, file count) come from
    `/api/code-search/repos/<repo>/stats` so this endpoint can stay
    fast even when a repo has 1M+ commits.
    """
    root = _repos_root(request)
    if not root.is_dir():
        return []
    out: list[dict] = []
    for entry in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        if not _is_git_repo(entry):
            continue
        branch = _git_out(entry, ["rev-parse", "--abbrev-ref", "HEAD"]) or "HEAD"
        last_line = _git_out(
            entry,
            ["log", "-1", "--format=%h%x09%an%x09%ae%x09%ar%x09%aI%x09%s"],
        )
        last: dict = {}
        if last_line:
            parts = last_line.split("\t", 5)
            if len(parts) == 6:
                last = {
                    "sha": parts[0],
                    "who": parts[1],
                    "email": parts[2],
                    "when": parts[3],
                    "when_iso": parts[4],
                    "subj": parts[5],
                }
        out.append({
            "name": entry.name,
            "branch": branch,
            "last": last,
        })
    return out


@router.get("/api/code-search/repos/{repo}/stats")
async def repo_stats(repo: str, request: Request) -> dict:
    """Heavier per-repo numbers. Cheap-ish but still subprocess heavy
    so cache aggressively on the client side."""
    root = _repos_root(request)
    repo_dir = _validate_repo(root, repo)
    commits = _git_out(repo_dir, ["rev-list", "--count", "HEAD"], timeout=10.0)
    contribs_out = _git_out(repo_dir, ["shortlog", "-sn", "HEAD"], timeout=15.0)
    contribs = sum(1 for line in contribs_out.splitlines() if line.strip())
    files_out = _git_out(repo_dir, ["ls-files"], timeout=15.0)
    files = sum(1 for line in files_out.splitlines() if line)
    clone = _git_out(repo_dir, ["config", "--get", "remote.origin.url"])
    return {
        "commits": int(commits) if commits.isdigit() else 0,
        "contribs": contribs,
        "files": files,
        "clone": clone,
    }


@router.get("/api/code-search/repos/{repo}/search")
async def search(
    repo: str,
    request: Request,
    q: str = "",
    mode: str = "filenames",
    limit: int = 100,
) -> dict:
    """Filename or code search.

    `mode=filenames`: substring match against `git ls-files` output.
    `mode=code`: `rg --max-count 50 -n --no-heading -- <q>` (or
                 `git grep` as a fallback if `rg` isn't installed).

    `limit` caps the result list size; the UI's results pane is
    paginated visually but we don't fetch beyond this.
    """
    if not q:
        return {"mode": mode, "results": [], "truncated": False}
    if mode not in ("filenames", "code"):
        raise HTTPException(status_code=400, detail=f"unknown mode: {mode!r}")
    root = _repos_root(request)
    repo_dir = _validate_repo(root, repo)
    limit = max(1, min(limit, 500))
    if mode == "filenames":
        return _search_filenames(repo_dir, q, limit)
    return _search_code(repo_dir, q, limit)


def _search_filenames(repo_dir: Path, q: str, limit: int) -> dict:
    files = _git_out(repo_dir, ["ls-files"], timeout=10.0).splitlines()
    q_low = q.lower()
    results: list[dict] = []
    for path in files:
        if not path:
            continue
        if q_low not in path.lower():
            continue
        # File size (best-effort — symlinks/large repos shouldn't break us).
        size = 0
        try:
            stat = (repo_dir / path).stat()
            size = stat.st_size
        except OSError:
            pass
        results.append({"path": path, "size": size})
        if len(results) >= limit:
            return {"mode": "filenames", "results": results, "truncated": True}
    return {"mode": "filenames", "results": results, "truncated": False}


def _search_code(repo_dir: Path, q: str, limit: int) -> dict:
    # Prefer ripgrep — faster, better defaults (respects .gitignore,
    # skips binary files). Fall back to `git grep` so a system without
    # ripgrep still gets a usable search.
    rg_path = shutil.which("rg")
    if rg_path:
        cmd = [
            rg_path,
            "--max-count", "20",
            "--max-columns", "300",
            "-n",
            "--no-heading",
            "--color", "never",
            "--",
            q,
            ".",
        ]
        try:
            proc = subprocess.run(
                cmd, cwd=str(repo_dir), capture_output=True, text=True,
                timeout=20.0,
            )
        except subprocess.TimeoutExpired:
            return {"mode": "code", "results": [], "truncated": True,
                    "error": "search timed out (>20s) — try a more specific query"}
    else:
        # `git grep` doesn't honor `.gitignore` directives separately —
        # it only searches tracked files, which is fine for this use.
        cmd = ["grep", "-n", "--max-count=20", "--", q]
        rc, stdout, stderr = _git(
            repo_dir,
            ["grep", "-n", "--max-count=20", "--", q],
            timeout=20.0,
        )
        proc = subprocess.CompletedProcess(args=cmd, returncode=rc, stdout=stdout, stderr=stderr)

    results: list[dict] = []
    truncated = False
    for line in proc.stdout.splitlines():
        if not line or line.startswith("Binary file"):
            continue
        # Lines come as `path:line:snippet` (or `./path:line:snippet`
        # under rg with the trailing `.` target).
        parts = line.split(":", 2)
        if len(parts) < 3:
            continue
        path, ln, snippet = parts
        if path.startswith("./"):
            path = path[2:]
        try:
            line_no = int(ln)
        except ValueError:
            continue
        results.append({
            "path": path,
            "line": line_no,
            "snippet": snippet[:300],
        })
        if len(results) >= limit:
            truncated = True
            break
    return {"mode": "code", "results": results, "truncated": truncated}


# Cap individual file reads so a stray 100MB blob doesn't OOM the lab.
_FILE_MAX_BYTES = 2 * 1024 * 1024  # 2 MB


@router.get("/api/code-search/repos/{repo}/file")
async def read_file(repo: str, path: str, request: Request) -> dict:
    root = _repos_root(request)
    repo_dir = _validate_repo(root, repo)
    target = _resolve_in_repo(repo_dir, path)
    if not target.is_file():
        raise HTTPException(status_code=404, detail="file not found")
    try:
        size = target.stat().st_size
    except OSError:
        size = 0
    if size > _FILE_MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"file too large ({size} bytes; cap {_FILE_MAX_BYTES})",
        )
    try:
        text = target.read_text(errors="replace")
    except (UnicodeDecodeError, OSError) as e:
        raise HTTPException(status_code=415, detail=f"unreadable: {e!s}")
    return {
        "path": path,
        "content": text,
        "lines": text.count("\n") + (0 if text.endswith("\n") or not text else 1),
        "size": size,
    }


@router.get("/api/code-search/repos/{repo}/log")
async def repo_log(
    repo: str,
    request: Request,
    path: Optional[str] = None,
    start: Optional[int] = None,
    end: Optional[int] = None,
    limit: int = 50,
) -> list[dict]:
    """Git log.

    * No `path`           → whole-repo log (newest commits first).
    * `path` only         → file history (`git log -- <path>`).
    * `path` + `start`/`end` → line-range history (`git log -L start,end:path`).
                            The output of `-L` interleaves diff hunks; we
                            extract only the commit headers with a
                            sentinel marker in `--pretty=format`.
    """
    root = _repos_root(request)
    repo_dir = _validate_repo(root, repo)
    limit = max(1, min(limit, 200))

    if path:
        _resolve_in_repo(repo_dir, path)  # validation only

    if path and start is not None and end is not None:
        if start < 1 or end < start:
            raise HTTPException(status_code=400, detail="invalid line range")
        # `-L` doesn't accept `--format`; use `--pretty=format:` with a
        # leading sentinel so we can grep out the commit headers and
        # ignore the diff body in the same stream.
        args = [
            "log",
            f"--max-count={limit}",
            "--pretty=format:__LAB_COMMIT__%h%x09%an%x09%ae%x09%ar%x09%aI%x09%s",
            f"-L{start},{end}:{path}",
        ]
        rc, stdout, stderr = _git(repo_dir, args, timeout=20.0)
        if rc != 0:
            raise HTTPException(status_code=400, detail=stderr.strip() or "git log -L failed")
        commits: list[dict] = []
        for line in stdout.splitlines():
            if not line.startswith("__LAB_COMMIT__"):
                continue
            parts = line[len("__LAB_COMMIT__"):].split("\t", 5)
            if len(parts) == 6:
                sha, who, email, when, when_iso, subj = parts
                commits.append({
                    "sha": sha, "who": who, "email": email,
                    "when": when, "when_iso": when_iso, "subj": subj,
                })
        return commits

    args = [
        "log",
        f"--max-count={limit}",
        "--format=%h%x09%an%x09%ae%x09%ar%x09%aI%x09%s",
    ]
    if path:
        args.extend(["--", path])
    rc, stdout, stderr = _git(repo_dir, args, timeout=15.0)
    if rc != 0:
        raise HTTPException(status_code=400, detail=stderr.strip() or "git log failed")
    commits = []
    for line in stdout.splitlines():
        parts = line.split("\t", 5)
        if len(parts) == 6:
            sha, who, email, when, when_iso, subj = parts
            commits.append({
                "sha": sha, "who": who, "email": email,
                "when": when, "when_iso": when_iso, "subj": subj,
            })
    return commits


@router.get("/api/code-search/repos/{repo}/commit/{sha}")
async def commit_detail(
    repo: str,
    sha: str,
    request: Request,
    path: Optional[str] = None,
) -> dict:
    """Commit metadata + diff. `path` narrows the diff to one file."""
    if not _SHA_RE.match(sha):
        raise HTTPException(status_code=400, detail="invalid sha")
    root = _repos_root(request)
    repo_dir = _validate_repo(root, repo)
    if path:
        _resolve_in_repo(repo_dir, path)

    # Metadata: full hash, author, ISO date, subject, body, on separate
    # lines using a control-character separator that's unlikely to
    # appear in commit text.
    meta_args = [
        "show", "-s",
        "--format=%H%n%an%n%ae%n%aI%n%ar%n%s%n%b",
        sha,
    ]
    rc, stdout, stderr = _git(repo_dir, meta_args, timeout=10.0)
    if rc != 0:
        raise HTTPException(status_code=404, detail=stderr.strip() or "commit not found")
    lines = stdout.split("\n")
    while len(lines) < 7:
        lines.append("")
    full_sha, who, email, when_iso, when, subj = lines[:6]
    body = "\n".join(lines[6:]).rstrip()

    # Diff (no color, suppress the metadata block — already have it).
    diff_args = ["show", "--format=", "--no-color", sha]
    if path:
        diff_args.extend(["--", path])
    rc_d, diff_out, _ = _git(repo_dir, diff_args, timeout=20.0)
    return {
        "sha": full_sha[:12] if full_sha else sha,
        "full_sha": full_sha,
        "who": who,
        "email": email,
        "when": when,
        "when_iso": when_iso,
        "subj": subj,
        "body": body,
        "diff": diff_out if rc_d == 0 else "",
    }
