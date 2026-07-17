"""gdiff-absorbed routes: project-info, project-actions, diffs, commits, notebooks, files, comments.

These came verbatim from apps/gdiff/server.py during the backend unification.
They share the same FastAPI app as the `lab-backend` routers so the dashboard,
per-project view, and CLI all run from a single process on :3333.
"""
from __future__ import annotations

import json
import mimetypes
import os
import subprocess
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from core import fsguard
from core.diff_parser import (
    get_branch,
    get_commit_diff,
    get_commits,
    get_diff,
    get_file_tree,
    get_notebook_diff,
    get_registered_repos,
    parse_notebook,
)


router = APIRouter()


def _with_symlink_fields(entry: dict, path: Path) -> dict:
    if not path.is_symlink():
        return entry
    entry["is_symlink"] = True
    try:
        entry["symlink_target"] = os.readlink(path)
    except OSError:
        pass
    return entry


def _monorepo_root() -> Path:
    """Honors ``LAB_ROOT`` (tests), else walks up from this file.

    Package sits at ``<root>/core/src/core/routes/diff.py``.
    """
    env_root = os.environ.get("LAB_ROOT")
    if env_root:
        return Path(env_root)
    return Path(__file__).resolve().parents[4]


def _resolve_project_path(path: str) -> Path:
    """Accept either an absolute project path or a bare project id.

    Bare ids are resolved to ``<monorepo>/projects/<id>``.
    """
    if path.startswith("/"):
        return Path(path)
    return _monorepo_root() / "projects" / path


def _read_project_info(project_path: Path) -> dict | None:
    """Read project metadata. Prefer new ``project.json`` over legacy ``.project.json``."""
    for name in ("project.json", ".project.json"):
        candidate = project_path / name
        if candidate.is_file():
            try:
                return json.loads(candidate.read_text())
            except (json.JSONDecodeError, ValueError):
                return None
    return None


def _read_project_actions(project_path: Path) -> list[dict]:
    """Read action items.

    Prefers the new ``tasks.json`` schema:
      {"next_id": N, "tasks": [{id, title, status, priority, ..., blocker, updated, ...}]}

    Falls back to the legacy ``actions.json`` schema (flat list of
    ``{id, text, status, updated, blocker?, artifacts?}``).

    Always returns a flat array in the legacy action shape (``text`` field
    derived from ``title``) so the existing UI consumes it unchanged.
    """
    tasks_json = project_path / "tasks.json"
    if tasks_json.is_file():
        try:
            data = json.loads(tasks_json.read_text())
        except (json.JSONDecodeError, ValueError):
            data = None
        if isinstance(data, dict) and isinstance(data.get("tasks"), list):
            actions = []
            for t in data["tasks"]:
                if not isinstance(t, dict):
                    continue
                actions.append({
                    "id": t.get("id"),
                    "text": t.get("title", ""),
                    "status": t.get("status", "todo"),
                    "updated": t.get("updated"),
                    "blocker": t.get("blocker"),
                    "priority": t.get("priority"),
                    "artifacts": t.get("artifacts", []),
                })
            return actions

    actions_json = project_path / "actions.json"
    if actions_json.is_file():
        try:
            data = json.loads(actions_json.read_text())
        except (json.JSONDecodeError, ValueError):
            return []
        if isinstance(data, list):
            return data
    return []


def _safe_path(repo: str, filepath: str) -> Path:
    """Resolve file path and ensure it's within the repo."""
    repo_path = Path(repo).resolve()
    file_path = (repo_path / filepath).resolve()
    if not str(file_path).startswith(str(repo_path)):
        raise HTTPException(status_code=400, detail="Path traversal not allowed")
    if not repo_path.is_dir():
        raise HTTPException(status_code=400, detail="Repo not found")
    return file_path


@router.get("/api/diff")
def api_diff(repo: str, type: str = "uncommitted", exclude: str | None = None):
    """Uncommitted/branch diff for ``repo``.

    ``exclude`` is a comma-separated list of path prefixes to omit from the
    diff (e.g. ``exclude=repositories`` for the Productivity self-view).
    """
    excl = [p for p in (exclude or "").split(",") if p.strip()]
    return get_diff(repo, type, exclude_paths=excl or None)


# ─── Git status for sidebar decorations (VS Code Explorer-style) ─────────
# Small in-process cache keyed by resolved directory; entries expire after a
# few seconds so the sidebar poll (every ~6s per client) rarely pays for more
# than one `git status` subprocess per tick across all clients.
_GIT_STATUS_TTL = 4.0
_GIT_STATUS_CACHE: dict[str, tuple[float, dict]] = {}
_GIT_STATUS_CACHE_MAX = 64

_GIT_STATUS_LETTER = {
    "M": "M", "T": "M", "U": "M",  # modified / type-change / conflict
    "A": "A",
    "D": "D",
    "R": "R", "C": "R",            # rename / copy
}


def _git_status_for_dir(key: str) -> dict:
    """Run ``git status --porcelain`` for directory ``key`` (any dir inside a
    repo — usually a project folder) and map paths relative to that dir."""
    empty = {"files": {}, "ignored": []}
    if not os.path.isdir(key):
        return empty

    def _git(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", "-C", key, *args],
            capture_output=True, text=True, timeout=3,
        )

    try:
        pre = _git("rev-parse", "--show-prefix")
        if pre.returncode != 0:
            return empty  # not a git repo — steady state, not an error
        prefix = pre.stdout.strip()
        st = _git(
            "status", "--porcelain=v1", "--untracked-files=normal",
            "--ignored=traditional", "--", ".",
        )
        if st.returncode != 0:
            return empty
    except (subprocess.TimeoutExpired, OSError):
        return empty

    files: dict[str, str] = {}
    ignored: list[str] = []
    for line in st.stdout.splitlines():
        if len(line) < 4:
            continue
        xy, rest = line[:2], line[3:]
        # Renames come as "R  old -> new"; decorate the new path.
        if " -> " in rest and (xy[0] in "RC" or xy[1] in "RC"):
            rest = rest.split(" -> ", 1)[1]
        # Paths with special chars come back C-quoted; strip the quotes
        # (good enough for display matching — escapes are left as-is).
        if rest.startswith('"') and rest.endswith('"'):
            rest = rest[1:-1]
        if prefix:
            if not rest.startswith(prefix):
                continue
            rest = rest[len(prefix):]
        rel = rest.rstrip("/")
        if not rel:
            continue
        if xy == "??":
            files[rel] = "U"
        elif xy == "!!":
            ignored.append(rest)
        else:
            c = xy[0] if xy[0] != " " else xy[1]
            files[rel] = _GIT_STATUS_LETTER.get(c, "M")
    return {"files": files, "ignored": ignored}


def _inside(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def _git_status_dir_allowed(resolved: Path, active_root: Path) -> bool:
    """Containment for /api/git-status: the active workspace is always in
    bounds; anything else must come from the app's own registry of pinned
    tabs/views and their repos (which legitimately live outside the
    workspace, e.g. the framework checkout itself)."""
    if _inside(resolved, active_root):
        return True
    # The Productivity self-view is rooted at the framework checkout —
    # the same path main.py injects into the template as MONOREPO_ROOT.
    try:
        from lab import paths as lab_paths

        if _inside(resolved, Path(lab_paths.find_framework_root()).resolve()):
            return True
    except Exception:
        pass
    try:
        for proj in get_registered_repos(active_root):
            candidates = [proj.get("path"), *(proj.get("repos") or [])]
            for c in candidates:
                if c and _inside(resolved, Path(str(c)).expanduser().resolve()):
                    return True
    except Exception:
        pass
    return False


@router.get("/api/git-status")
def api_git_status(repo: str, request: Request):
    """Per-file git status for the directory ``repo``.

    Returns ``{"files": {"rel/path": "M"|"A"|"D"|"R"|"U"}, "ignored":
    ["rel/prefix", ...]}`` with paths relative to the requested directory
    (not the repo root). ``U`` = untracked; a fully-untracked or ignored
    directory appears as a single entry covering everything under it.
    Non-repo directories return empty maps.

    ``repo`` may be absolute (the sidebar passes the project's absolute
    path) or workspace-relative. The resolved directory must sit inside
    the active workspace or inside a location the app itself registers
    (pinned tabs/views and their repos can live outside the workspace) —
    this endpoint must not disclose status for arbitrary directories on
    the machine.
    """
    root = Path(request.app.state.index_cache.root).expanduser().resolve()
    candidate = Path(repo) if repo.startswith("/") else root / repo
    try:
        resolved = candidate.expanduser().resolve()
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"bad repo path: {exc}") from exc
    if not _git_status_dir_allowed(resolved, root):
        raise HTTPException(status_code=400, detail="repo escapes workspace")
    key = str(resolved)
    now = time.time()
    hit = _GIT_STATUS_CACHE.get(key)
    if hit and now - hit[0] < _GIT_STATUS_TTL:
        return hit[1]
    result = _git_status_for_dir(key)
    if len(_GIT_STATUS_CACHE) >= _GIT_STATUS_CACHE_MAX:
        # Drop expired entries first; if all fresh, drop the oldest.
        for k in [k for k, (ts, _) in _GIT_STATUS_CACHE.items()
                  if now - ts >= _GIT_STATUS_TTL]:
            _GIT_STATUS_CACHE.pop(k, None)
        if len(_GIT_STATUS_CACHE) >= _GIT_STATUS_CACHE_MAX:
            oldest = min(_GIT_STATUS_CACHE, key=lambda k: _GIT_STATUS_CACHE[k][0])
            _GIT_STATUS_CACHE.pop(oldest, None)
    _GIT_STATUS_CACHE[key] = (now, result)
    return result


@router.get("/api/notebook")
def api_notebook(repo: str, path: str):
    file_path = _safe_path(repo, path)
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return parse_notebook(str(file_path))


@router.get("/api/notebook-diff")
def api_notebook_diff(repo: str, path: str, type: str = "uncommitted"):
    return get_notebook_diff(repo, path, type)


@router.get("/api/commits")
def api_commits(repo: str, count: int = 20, exclude: str | None = None):
    """Recent commits for ``repo``; ``exclude`` behaves like /api/diff's."""
    excl = [p for p in (exclude or "").split(",") if p.strip()]
    return get_commits(repo, count, exclude_paths=excl or None)


@router.get("/api/commit-diff")
def api_commit_diff(repo: str, sha: str):
    return get_commit_diff(repo, sha)


@router.get("/api/tree")
def api_tree(repo: str):
    return get_file_tree(repo)


@router.get("/api/repos")
def api_repos(request: Request):
    projects = get_registered_repos(request.app.state.index_cache.root)
    result = []
    for proj in projects:
        repos = []
        for repo_path in proj["repos"]:
            try:
                branch = get_branch(repo_path)
            except Exception:
                branch = "unknown"
            repos.append({"path": repo_path, "name": Path(repo_path).name, "branch": branch})
        result.append({
            "name": proj["name"],
            "is_project": proj["is_project"],
            "path": proj["path"],
            "repos": repos,
            "tab_open": bool(proj.get("tab_open", False)),
        })
    return result


@router.get("/api/project-info")
def api_project_info(path: str):
    project_path = _resolve_project_path(path)
    info = _read_project_info(project_path)
    if info is None:
        raise HTTPException(status_code=404, detail="No project.json found")
    return info


class ProjectInfoBody(BaseModel):
    path: str
    data: dict


@router.put("/api/project-info")
def update_project_info(body: ProjectInfoBody):
    project_path = _resolve_project_path(body.path)
    target = project_path / "project.json"
    if not target.is_file():
        legacy = project_path / ".project.json"
        if legacy.is_file():
            target = legacy
    if not target.is_file():
        raise HTTPException(status_code=404, detail="No project.json found")
    target.write_text(json.dumps(body.data, indent=2) + "\n")
    return {"ok": True}


@router.get("/api/project-actions")
def api_project_actions(path: str):
    project_path = _resolve_project_path(path)
    return _read_project_actions(project_path)


@router.get("/api/project-alerts")
def api_project_alerts(path: str):
    project_path = _resolve_project_path(path)
    alerts_json = project_path / "alerts.json"
    if not alerts_json.is_file():
        return []
    try:
        return json.loads(alerts_json.read_text())
    except (json.JSONDecodeError, ValueError):
        return []


@router.get("/api/project-artifacts")
def api_project_artifacts(path: str):
    project_path = _resolve_project_path(path)
    artifacts_json = project_path / "artifacts.json"
    if not artifacts_json.is_file():
        return []
    try:
        return json.loads(artifacts_json.read_text())
    except (json.JSONDecodeError, ValueError):
        return []


@router.get("/api/project-onepager")
def api_project_onepager(path: str):
    project_path = _resolve_project_path(path)
    for rel in ("docs/one-pager.md", "one-pager.md"):
        candidate = project_path / rel
        if candidate.is_file():
            return {"content": candidate.read_text()}
    return {"content": ""}


@router.get("/api/project-files")
def api_project_files(path: str, request: Request, include_dotfiles: bool = False):
    """List all files in a project directory as a flat list with relative paths."""
    project_path = Path(path)
    if not project_path.is_dir():
        return []
    IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"}
    # `worktrees/` is the dedicated subfolder for MP worktrees — each one is
    # a full repo checkout, so listing them in the project's file sidebar
    # would drown out docs/notes. Accessible via the Repositories panel +
    # diff tabs instead.
    SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv",
                 ".mypy_cache", ".pytest_cache", "build", "dist", ".tox", ".eggs",
                 "skills", "worktrees"}
    files = []
    MAX_DEPTH = 5

    # Cheap O(1) check against the in-memory tracker maintained by
    # routes/nb_exec.py. The previous file-scan implementation skipped
    # notebooks larger than 5 MB (e.g. Plotly-heavy notebooks easily clear
    # that), which left the sidebar dot dark for exactly the notebooks
    # users were most likely to want a "running" indicator on. The tracker
    # naturally clears on server restart — the Darwin subprocess also dies
    # then, so the two stay consistent.
    from core.routes.nb_exec import is_path_pending as _ipynb_is_pending  # noqa: PLC0415

    def scan(dir_path, depth=0):
        if depth > MAX_DEPTH:
            return
        try:
            children = sorted(dir_path.iterdir())
        except PermissionError:
            return
        for child in children:
            if not include_dotfiles and child.name.startswith("."):
                continue
            child_is_symlink = child.is_symlink()
            if child.is_file():
                rel = str(child.relative_to(project_path))
                ftype = "image" if child.suffix.lower() in IMAGE_EXTS else "file"
                entry = {"name": rel, "path": rel, "type": ftype}
                _with_symlink_fields(entry, child)
                # Flag .ipynb files that currently have a running cell
                # so the sidebar can render a blinking activity dot
                # without each client polling every notebook. Also include
                # the file mtime so the client can compare it against a
                # per-file "last viewed" timestamp in localStorage and
                # show a separate "new results" dot for notebooks whose
                # outputs the user hasn't acknowledged yet.
                if child.suffix.lower() == ".ipynb":
                    try:
                        entry["mtime"] = child.stat().st_mtime
                    except OSError:
                        pass
                    if _ipynb_is_pending(child):
                        entry["pending"] = True
                files.append(entry)
            elif child.is_dir():
                if child_is_symlink:
                    rel = str(child.relative_to(project_path))
                    entry = {"name": rel, "path": rel, "type": "dir"}
                    _with_symlink_fields(entry, child)
                    files.append(entry)
                if child.name not in SKIP_DIRS:
                    scan(child, depth + 1)
            elif child_is_symlink:
                # Broken symlink: still surface the row so the sidebar can
                # distinguish it from an absent file/folder.
                rel = str(child.relative_to(project_path))
                entry = {"name": rel, "path": rel, "type": "file", "broken": True}
                _with_symlink_fields(entry, child)
                files.append(entry)

    workspace_root: Path = request.app.state.index_cache.root
    fsguard.guarded(workspace_root, scan, project_path)
    return files


@router.get("/api/project-file")
def api_project_file(path: str, file: str):
    """Read a project-level file.

    Security: path-traversal is enforced on the *input* ``file`` parameter
    (no absolute paths, no ``..`` segments). We deliberately do NOT reject
    symlinks whose resolved target lives outside the project — the shared
    ``CLAUDE.md`` in every project is a symlink to
    ``content/skills/project-CLAUDE.md`` and we want it to read cleanly.
    """
    if file.startswith("/") or ".." in Path(file).parts:
        raise HTTPException(status_code=400, detail="Path traversal not allowed")
    project_path = Path(path).resolve()
    file_path = project_path / file  # no .resolve(): follow-through happens on I/O
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    try:
        content = file_path.read_text()
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="Binary file")
    return {"content": content, "name": file}


@router.get("/api/project-mtime")
def api_project_mtime(path: str, request: Request):
    """Return the latest mtime across files in a project directory.

    The client polls this every 2s from the project / self view to decide
    whether to refresh. The OLD implementation used ``rglob("*")`` with no
    skip-list and no depth cap, so on the self-view (``path = monorepo
    root``) it walked ``apps/*/.venv/``, ``repositories/``, and every
    cached site-packages tree — stalling the event loop for 20+ seconds
    every 2 seconds. That was the "reload takes forever" regression.

    Fix: mirror the same SKIP_DIRS + dotfile skip + MAX_DEPTH the sibling
    ``/api/project-files`` already uses so the two endpoints agree on
    "what counts as part of the project". On the self-view this drops
    the walk from ~25s to ~100ms.
    """
    project_path = Path(path)
    if not project_path.is_dir():
        # A missing directory is an expected steady state, not an error: a
        # browser tab can outlive its project (deleted, or on an unplugged
        # external volume) and keep polling for days — as a 404 each poll
        # logged a WARNING, thousands of pure noise lines. ``null`` tells
        # the client "nothing to compare against"; old clients treat it as
        # a harmless no-op (``null > x`` is false).
        return {"mtime": None}
    # Must stay in sync with api_project_files above — clients assume the
    # same tree shape (sidebar vs. mtime poll).
    SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv",
                 ".mypy_cache", ".pytest_cache", "build", "dist", ".tox",
                 ".eggs", "skills", "worktrees"}
    MAX_DEPTH = 5

    latest = project_path.stat().st_mtime

    def scan(dir_path: Path, depth: int) -> None:
        nonlocal latest
        if depth > MAX_DEPTH:
            return
        try:
            children = list(dir_path.iterdir())
        except (PermissionError, OSError):
            return
        for child in children:
            if child.name.startswith("."):
                continue
            try:
                if child.is_file():
                    latest = max(latest, child.stat().st_mtime)
                elif child.is_dir() and child.name not in SKIP_DIRS:
                    latest = max(latest, child.stat().st_mtime)
                    scan(child, depth + 1)
            except OSError:
                # Broken symlink / disappeared mid-walk — skip.
                continue

    workspace_root: Path = request.app.state.index_cache.root
    fsguard.guarded(workspace_root, scan, project_path, 0)
    return {"mtime": latest}


@router.get("/api/project-asset")
def api_project_asset(path: str, file: str):
    """Serve a static file (image, etc.) from a project directory. Same
    input-only traversal check as ``/api/project-file``."""
    if file.startswith("/") or ".." in Path(file).parts:
        raise HTTPException(status_code=400, detail="Path traversal not allowed")
    project_path = Path(path).resolve()
    file_path = project_path / file
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    media_type, _ = mimetypes.guess_type(str(file_path))
    return FileResponse(file_path, media_type=media_type)


class ProjectFileBody(BaseModel):
    path: str  # project path
    file: str  # file path relative to project
    content: str


@router.put("/api/project-file")
def update_project_file(body: ProjectFileBody):
    """Save a project-level file."""
    project_path = Path(body.path).resolve()
    file_path = (project_path / body.file).resolve()
    if not str(file_path).startswith(str(project_path)):
        raise HTTPException(status_code=400, detail="Path traversal not allowed")
    if not file_path.parent.is_dir():
        file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(body.content)
    return {"ok": True}


@router.get("/api/project-comments")
def api_project_comments(path: str):
    """Read comments.json from project."""
    comments_path = Path(path) / "comments.json"
    if not comments_path.is_file():
        return []
    try:
        return json.loads(comments_path.read_text())
    except (json.JSONDecodeError, ValueError):
        return []


class CommentBody(BaseModel):
    path: str            # project path (holds comments.json)
    file: str            # file the comment is on
    text: str            # selected text (doc) or line content (code)
    comment: str         # the user's note
    # Optional context for code/diff comments — all default to None so doc
    # comments continue to round-trip unchanged.
    kind: str | None = None        # 'doc' (default when absent) | 'code'
    repo: str | None = None        # relative repo/worktree path within the project
    scope: str | None = None       # 'uncommitted' | 'branch' | 'commit'
    sha: str | None = None         # commit SHA (only when scope='commit')
    line: int | None = None        # line number the comment targets
    side: str | None = None        # 'old' | 'new' (which side of the diff)


@router.post("/api/project-comments")
def add_project_comment(body: CommentBody):
    """Add a comment to comments.json.

    Doc comments pass only the original fields (kind left unset). Code /
    diff comments pass kind='code' plus repo/scope/sha/line/side so they
    can be rendered on the right diff line later — even if the user is
    now looking at a different commit or branch.
    """
    import datetime as _dt

    comments_path = Path(body.path) / "comments.json"
    comments = []
    if comments_path.is_file():
        comments = json.loads(comments_path.read_text())
    entry: dict = {
        "id": int(time.time() * 1000),
        "file": body.file,
        "text": body.text,
        "comment": body.comment,
        "created": _dt.date.today().isoformat(),
    }
    # Persist optional diff-context fields when the client sends them.
    for k in ("kind", "repo", "scope", "sha", "line", "side"):
        v = getattr(body, k)
        if v is not None and v != "":
            entry[k] = v
    comments.append(entry)
    comments_path.write_text(json.dumps(comments, indent=2))
    return {"ok": True}


class CommentDeleteBody(BaseModel):
    path: str
    comment_id: int


@router.delete("/api/project-comments")
def delete_project_comment(body: CommentDeleteBody):
    """Delete (resolve) a comment."""
    comments_path = Path(body.path) / "comments.json"
    if not comments_path.is_file():
        return {"ok": True}
    comments = json.loads(comments_path.read_text())
    comments = [c for c in comments if c.get("id") != body.comment_id]
    comments_path.write_text(json.dumps(comments, indent=2))
    return {"ok": True}


class ActionCompleteBody(BaseModel):
    path: str
    action_id: int
    artifacts: list[str] = []


@router.post("/api/project-action-complete")
def complete_project_action(body: ActionCompleteBody):
    """Mark an action/task item as done with optional artifacts.

    Writes back to the new ``tasks.json`` schema when present; falls back
    to the legacy ``actions.json`` array for older projects.
    """
    import datetime

    project_path = _resolve_project_path(body.path)

    tasks_path = project_path / "tasks.json"
    if tasks_path.is_file():
        data = json.loads(tasks_path.read_text())
        today = datetime.date.today().isoformat()
        if isinstance(data, dict) and isinstance(data.get("tasks"), list):
            for t in data["tasks"]:
                if t.get("id") == body.action_id:
                    t["status"] = "done"
                    t["updated"] = today
                    t["closed_at"] = today
                    if body.artifacts:
                        t["artifacts"] = body.artifacts
                    break
            tasks_path.write_text(json.dumps(data, indent=2) + "\n")
            return {"ok": True}

    actions_path = project_path / "actions.json"
    if not actions_path.is_file():
        raise HTTPException(status_code=404, detail="No tasks.json or actions.json found")
    actions = json.loads(actions_path.read_text())
    for a in actions:
        if a.get("id") == body.action_id:
            a["status"] = "done"
            a["updated"] = datetime.date.today().isoformat()
            if body.artifacts:
                a["artifacts"] = body.artifacts
            break
    actions_path.write_text(json.dumps(actions, indent=2))
    return {"ok": True}


class FileBody(BaseModel):
    repo: str
    path: str
    content: str


@router.get("/api/file")
def get_file(repo: str, path: str):
    file_path = _safe_path(repo, path)
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    try:
        content = file_path.read_text()
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="Binary file")
    return {"content": content, "path": path}


@router.put("/api/file")
def update_file(body: FileBody):
    file_path = _safe_path(body.repo, body.path)
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    file_path.write_text(body.content)
    return {"ok": True}


@router.post("/api/file")
def create_file(body: FileBody):
    file_path = _safe_path(body.repo, body.path)
    if file_path.exists():
        raise HTTPException(status_code=409, detail="File already exists")
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(body.content)
    return {"ok": True}


@router.delete("/api/file")
def delete_file(repo: str, path: str):
    file_path = _safe_path(repo, path)
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    file_path.unlink()
    return {"ok": True}
