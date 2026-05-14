"""gdiff-absorbed routes: project-info, project-actions, diffs, commits, notebooks, files, comments.

These came verbatim from apps/gdiff/server.py during the backend unification.
They share the same FastAPI app as the `lab-backend` routers so the dashboard,
per-project view, and CLI all run from a single process on :3333.
"""
from __future__ import annotations

import json
import mimetypes
import os
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from server.diff_parser import (
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


def _monorepo_root() -> Path:
    """Honors ``LAB_ROOT`` (tests), else walks up from this file.

    Package sits at ``<root>/apps/server/src/server/routes/diff.py``.
    """
    env_root = os.environ.get("LAB_ROOT")
    if env_root:
        return Path(env_root)
    return Path(__file__).resolve().parents[5]


def _resolve_project_path(path: str) -> Path:
    """Accept either an absolute project path or a bare project id.

    Bare ids are resolved to ``<monorepo>/content/projects/<id>``.
    """
    if path.startswith("/"):
        return Path(path)
    return _monorepo_root() / "content" / "projects" / path


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
async def api_diff(repo: str, type: str = "uncommitted", exclude: str | None = None):
    """Uncommitted/branch diff for ``repo``.

    ``exclude`` is a comma-separated list of path prefixes to omit from the
    diff (e.g. ``exclude=repositories`` for the Productivity self-view).
    """
    excl = [p for p in (exclude or "").split(",") if p.strip()]
    return get_diff(repo, type, exclude_paths=excl or None)


@router.get("/api/notebook")
async def api_notebook(repo: str, path: str):
    file_path = _safe_path(repo, path)
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return parse_notebook(str(file_path))


@router.get("/api/notebook-diff")
async def api_notebook_diff(repo: str, path: str, type: str = "uncommitted"):
    return get_notebook_diff(repo, path, type)


@router.get("/api/commits")
async def api_commits(repo: str, count: int = 20, exclude: str | None = None):
    """Recent commits for ``repo``; ``exclude`` behaves like /api/diff's."""
    excl = [p for p in (exclude or "").split(",") if p.strip()]
    return get_commits(repo, count, exclude_paths=excl or None)


@router.get("/api/commit-diff")
async def api_commit_diff(repo: str, sha: str):
    return get_commit_diff(repo, sha)


@router.get("/api/tree")
async def api_tree(repo: str):
    return get_file_tree(repo)


@router.get("/api/repos")
async def api_repos():
    projects = get_registered_repos()
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
async def api_project_info(path: str):
    project_path = _resolve_project_path(path)
    info = _read_project_info(project_path)
    if info is None:
        raise HTTPException(status_code=404, detail="No project.json found")
    return info


class ProjectInfoBody(BaseModel):
    path: str
    data: dict


@router.put("/api/project-info")
async def update_project_info(body: ProjectInfoBody):
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
async def api_project_actions(path: str):
    project_path = _resolve_project_path(path)
    return _read_project_actions(project_path)


@router.get("/api/project-alerts")
async def api_project_alerts(path: str):
    project_path = _resolve_project_path(path)
    alerts_json = project_path / "alerts.json"
    if not alerts_json.is_file():
        return []
    try:
        return json.loads(alerts_json.read_text())
    except (json.JSONDecodeError, ValueError):
        return []


@router.get("/api/project-artifacts")
async def api_project_artifacts(path: str):
    project_path = _resolve_project_path(path)
    artifacts_json = project_path / "artifacts.json"
    if not artifacts_json.is_file():
        return []
    try:
        return json.loads(artifacts_json.read_text())
    except (json.JSONDecodeError, ValueError):
        return []


@router.get("/api/project-onepager")
async def api_project_onepager(path: str):
    project_path = _resolve_project_path(path)
    for rel in ("docs/one-pager.md", "one-pager.md"):
        candidate = project_path / rel
        if candidate.is_file():
            return {"content": candidate.read_text()}
    return {"content": ""}


@router.get("/api/project-files")
async def api_project_files(path: str, include_dotfiles: bool = False):
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
    from server.routes.nb_exec import is_path_pending as _ipynb_is_pending  # noqa: PLC0415

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
            if child.is_file():
                rel = str(child.relative_to(project_path))
                ftype = "image" if child.suffix.lower() in IMAGE_EXTS else "file"
                entry = {"name": rel, "path": rel, "type": ftype}
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
            elif child.is_dir() and child.name not in SKIP_DIRS:
                scan(child, depth + 1)

    scan(project_path)
    return files


@router.get("/api/project-file")
async def api_project_file(path: str, file: str):
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
async def api_project_mtime(path: str):
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
        raise HTTPException(status_code=404, detail="Project not found")
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

    scan(project_path, 0)
    return {"mtime": latest}


@router.get("/api/project-asset")
async def api_project_asset(path: str, file: str):
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
async def update_project_file(body: ProjectFileBody):
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
async def api_project_comments(path: str):
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
async def add_project_comment(body: CommentBody):
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
async def delete_project_comment(body: CommentDeleteBody):
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
async def complete_project_action(body: ActionCompleteBody):
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
async def get_file(repo: str, path: str):
    file_path = _safe_path(repo, path)
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    try:
        content = file_path.read_text()
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="Binary file")
    return {"content": content, "path": path}


@router.put("/api/file")
async def update_file(body: FileBody):
    file_path = _safe_path(body.repo, body.path)
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    file_path.write_text(body.content)
    return {"ok": True}


@router.post("/api/file")
async def create_file(body: FileBody):
    file_path = _safe_path(body.repo, body.path)
    if file_path.exists():
        raise HTTPException(status_code=409, detail="File already exists")
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(body.content)
    return {"ok": True}


@router.delete("/api/file")
async def delete_file(repo: str, path: str):
    file_path = _safe_path(repo, path)
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    file_path.unlink()
    return {"ok": True}
