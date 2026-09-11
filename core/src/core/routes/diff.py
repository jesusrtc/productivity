"""gdiff-absorbed routes: workspace-info, workspace-actions, diffs, commits, notebooks, files, comments.

These came verbatim from apps/gdiff/server.py during the backend unification.
They share the same FastAPI app as the `lab-backend` routers so the dashboard,
per-workspace view, and CLI all run from a single process on :3333.
"""
from __future__ import annotations

from lab import naming

import json
import mimetypes
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from core import auth, fsguard, server_config
from core.diff_parser import (
    diff_notebook_cells,
    get_branch,
    get_commit_diff,
    get_commits,
    get_diff,
    get_file_tree,
    get_notebook_diff,
    get_registered_repos,
    parse_unified_diff,
    parse_notebook,
    parse_notebook_content,
)


router = APIRouter()


# Keep a hard runaway guard, but leave enough room for ordinary source trees.
# Five levels was too shallow for real nested checkouts such as
# repositories/queries/forge/experimental/cached-queries/cached_queries/tools.
# Nested Git roots still reset the budget below, but correctness must not
# depend on whether a checkout uses a `.git` directory, a `.git` file, or
# metadata that is unavailable to the server process.
_WORKSPACE_SCAN_MAX_DEPTH = 16
_WORKSPACE_SCAN_SKIP_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv",
    ".mypy_cache", ".pytest_cache", "build", "dist", ".tox", ".eggs",
    "skills", "worktrees",
}


def _workspace_scan_child_depth(directory: Path, depth: int) -> int:
    """Give each nested Git checkout its own bounded scan-depth budget."""
    try:
        if (directory / ".git").exists():
            return 0
    except OSError:
        pass
    return depth + 1


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


def _resolve_workspace_path(path: str) -> Path:
    """Accept either an absolute workspace path or a bare workspace id.

    Bare ids are resolved to ``<monorepo>/workspaces/<id>``.
    """
    if path.startswith("/"):
        return Path(path)
    return naming.workspaces_dir(_monorepo_root()) / path


def _read_workspace_info(workspace_path: Path) -> dict | None:
    """Read workspace metadata. Prefer new ``workspace.json`` over legacy ``.workspace.json``."""
    for name in ("workspace.json", "project.json", ".workspace.json", ".project.json"):
        candidate = workspace_path / name
        if candidate.is_file():
            try:
                info = json.loads(candidate.read_text())
            except (json.JSONDecodeError, ValueError):
                return None
            config_path = workspace_path / server_config.CONFIG_FILENAME
            if config_path.is_file() and isinstance(info, dict):
                info = dict(info)
                try:
                    servers, source = server_config.read_server_config(workspace_path)
                    info["proxies"] = servers
                    info["server_config_source"] = source
                except server_config.ServerConfigError as exc:
                    info["proxies"] = []
                    info["server_config_source"] = server_config.CONFIG_FILENAME
                    info["server_config_error"] = str(exc)
            return info
    return None


def _read_workspace_actions(workspace_path: Path) -> list[dict]:
    """Read action items.

    Prefers the new ``tasks.json`` schema:
      {"next_id": N, "tasks": [{id, title, status, priority, ..., blocker, updated, ...}]}

    Falls back to the legacy ``actions.json`` schema (flat list of
    ``{id, text, status, updated, blocker?, artifacts?}``).

    Always returns a flat array in the legacy action shape (``text`` field
    derived from ``title``) so the existing UI consumes it unchanged.
    """
    tasks_json = workspace_path / "tasks.json"
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

    actions_json = workspace_path / "actions.json"
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
    repo — usually a workspace folder) and map paths relative to that dir."""
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
    """Containment for /api/git-status: the active vault is always in
    bounds; registered vaults and the app's own pinned tabs/views are
    also valid because all of them can remain open simultaneously."""
    if _inside(resolved, active_root):
        return True
    try:
        from lab import paths as lab_paths

        for vault in lab_paths.read_vault_registry().get("vaults", []):
            vault_path = vault.get("path") if isinstance(vault, dict) else None
            if vault_path and _inside(
                resolved, Path(str(vault_path)).expanduser().resolve(),
            ):
                return True
    except Exception:
        pass
    # The Productivity self-view is rooted at the framework checkout —
    # the same path main.py injects into the template as MONOREPO_ROOT.
    try:
        from lab import paths as lab_paths

        if _inside(resolved, Path(lab_paths.find_framework_root()).resolve()):
            return True
    except Exception:
        pass
    # The global Assistant database is a client-selected, admin-only workspace
    # root. Its sidebar uses the same recent/Git endpoints as normal workspaces.
    try:
        from lab import paths as lab_paths

        assistant = lab_paths.assistant_root()
        if assistant is not None and _inside(resolved, assistant.resolve()):
            return True
    except Exception:
        pass
    try:
        for workspace in get_registered_repos(active_root):
            candidates = [workspace.get("path"), *(workspace.get("repos") or [])]
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

    ``repo`` may be absolute (the sidebar passes the workspace's absolute
    path) or vault-relative. The resolved directory must sit inside
    the active vault, another registered vault, or a location the
    app itself registers (pinned tabs/views and their repos can live outside
    a vault). This endpoint must not disclose status for arbitrary
    directories on the machine.
    """
    root = auth.request_root(request)
    candidate = Path(repo) if repo.startswith("/") else root / repo
    try:
        resolved = candidate.expanduser().resolve()
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"bad repo path: {exc}") from exc
    if not _git_status_dir_allowed(resolved, root):
        raise HTTPException(status_code=400, detail="repo escapes vault")
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


_SIDEBAR_RECENT_GIT_MODES = {"uncommitted", "origin-main", "last-2-commits"}


def _sidebar_git_run(directory: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", directory, "-c", "core.quotepath=false", *args],
        capture_output=True,
        timeout=5,
    )


def _sidebar_git_paths(result: subprocess.CompletedProcess) -> list[str]:
    if result.returncode != 0:
        return []
    decoded = result.stdout.decode("utf-8", errors="surrogateescape")
    return [path.strip("\n") for path in decoded.split("\0") if path.strip("\n")]


def _sidebar_git_recent_files(directory: str, mode: str) -> dict:
    try:
        inside = _sidebar_git_run(directory, "rev-parse", "--is-inside-work-tree")
    except (subprocess.TimeoutExpired, OSError):
        return {"files": [], "mode": mode, "available": False}
    if inside.returncode != 0 or inside.stdout.strip() != b"true":
        return {"files": [], "mode": mode, "available": False}

    paths: list[str] = []
    seen: set[str] = set()

    def add(result: subprocess.CompletedProcess) -> None:
        for path in _sidebar_git_paths(result):
            if path not in seen:
                seen.add(path)
                paths.append(path)

    try:
        if mode == "uncommitted":
            tracked = _sidebar_git_run(
                directory, "diff", "--name-only", "-z", "--relative", "HEAD", "--", ".",
            )
            if tracked.returncode != 0:  # unborn repository
                tracked = _sidebar_git_run(
                    directory, "diff", "--cached", "--name-only", "-z", "--relative", "--", ".",
                )
            add(tracked)
            add(_sidebar_git_run(
                directory, "ls-files", "--others", "--exclude-standard", "-z", "--", ".",
            ))
        elif mode == "origin-main":
            base_ref = "refs/remotes/origin/main"
            exists = _sidebar_git_run(directory, "rev-parse", "--verify", "--quiet", base_ref)
            if exists.returncode != 0:
                return {
                    "files": [], "mode": mode, "available": False,
                    "base_ref": "origin/main",
                }
            add(_sidebar_git_run(
                directory, "diff", "--name-only", "-z", "--relative", "origin/main", "--", ".",
            ))
            add(_sidebar_git_run(
                directory, "ls-files", "--others", "--exclude-standard", "-z", "--", ".",
            ))
        else:  # last-2-commits
            revisions = _sidebar_git_run(directory, "rev-list", "--max-count=2", "HEAD")
            if revisions.returncode != 0:
                return {"files": [], "mode": mode, "available": False}
            for sha in revisions.stdout.decode("ascii", errors="ignore").splitlines():
                if sha:
                    add(_sidebar_git_run(
                        directory, "show", "-m", "--first-parent", "--pretty=format:",
                        "--name-only", "-z", "--relative", sha, "--", ".",
                    ))
    except (subprocess.TimeoutExpired, OSError):
        return {"files": [], "mode": mode, "available": False}

    result = {"files": paths, "mode": mode, "available": True}
    if mode == "origin-main":
        result["base_ref"] = "origin/main"
    return result


@router.get("/api/sidebar-recent-files")
def api_sidebar_recent_files(repo: str, mode: str, request: Request):
    """File paths for one Git-backed Recently updated quick selector."""
    if mode not in _SIDEBAR_RECENT_GIT_MODES:
        raise HTTPException(status_code=400, detail="Unsupported recent file mode")
    root = auth.request_root(request)
    candidate = Path(repo) if repo.startswith("/") else root / repo
    try:
        resolved = candidate.expanduser().resolve()
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"bad repo path: {exc}") from exc
    if not resolved.is_dir() or not _git_status_dir_allowed(resolved, root):
        raise HTTPException(status_code=400, detail="repo escapes vault")
    return _sidebar_git_recent_files(str(resolved), mode)


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
    workspaces = get_registered_repos(auth.request_root(request))
    result = []
    for workspace in workspaces:
        repos = []
        for repo_path in workspace["repos"]:
            try:
                branch = get_branch(repo_path)
            except Exception:
                branch = "unknown"
            repos.append({"path": repo_path, "name": Path(repo_path).name, "branch": branch})
        result.append({
            "name": workspace["name"],
            "display_name": workspace.get("display_name", workspace["name"]),
            "is_workspace": workspace["is_workspace"],
            "path": workspace["path"],
            "repos": repos,
            "tab_open": bool(workspace.get("tab_open", False)),
        })
    return result


@router.get("/api/workspace-info")
def api_workspace_info(path: str, request: Request):
    workspace_path = _resolve_workspace_path(path)
    from lab import paths

    assistant_root = paths.assistant_root()
    if assistant_root is not None and workspace_path.resolve() == assistant_root.resolve():
        auth.require_admin(request)
        # Assistant owns Markdown rather than workspace.json. The shared
        # document viewer still asks for optional artifact metadata.
        return {"id": "__assistant__", "name": "Assistant", "artifacts": []}
    info = _read_workspace_info(workspace_path)
    if info is None:
        raise HTTPException(status_code=404, detail="No workspace.json found")
    return info


class WorkspaceInfoBody(BaseModel):
    path: str
    data: dict


@router.put("/api/workspace-info")
def update_workspace_info(body: WorkspaceInfoBody):
    workspace_path = _resolve_workspace_path(body.path)
    target = naming.workspace_metadata_file(workspace_path)
    if not target.is_file():
        legacy = workspace_path / ".workspace.json"
        if legacy.is_file():
            target = legacy
    if not target.is_file():
        raise HTTPException(status_code=404, detail="No workspace.json found")
    target.write_text(json.dumps(body.data, indent=2) + "\n")
    return {"ok": True}


@router.get("/api/workspace-actions")
def api_workspace_actions(path: str):
    workspace_path = _resolve_workspace_path(path)
    return _read_workspace_actions(workspace_path)


@router.get("/api/workspace-alerts")
def api_workspace_alerts(path: str):
    workspace_path = _resolve_workspace_path(path)
    alerts_json = workspace_path / "alerts.json"
    if not alerts_json.is_file():
        return []
    try:
        return json.loads(alerts_json.read_text())
    except (json.JSONDecodeError, ValueError):
        return []


@router.get("/api/workspace-artifacts")
def api_workspace_artifacts(path: str):
    workspace_path = _resolve_workspace_path(path)
    artifacts_json = workspace_path / "artifacts.json"
    if not artifacts_json.is_file():
        return []
    try:
        return json.loads(artifacts_json.read_text())
    except (json.JSONDecodeError, ValueError):
        return []


@router.get("/api/workspace-onepager")
def api_workspace_onepager(path: str):
    workspace_path = _resolve_workspace_path(path)
    for rel in ("docs/one-pager.md", "one-pager.md"):
        candidate = workspace_path / rel
        if candidate.is_file():
            return {"content": candidate.read_text()}
    return {"content": ""}


@router.get("/api/workspace-files")
def api_workspace_files(path: str, request: Request, include_dotfiles: bool = False):
    """List all files in a workspace directory as a flat list with relative paths."""
    workspace_path = Path(path)
    if not workspace_path.is_dir():
        return []
    IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"}
    # `worktrees/` is the dedicated subfolder for MP worktrees — each one is
    # a full repo checkout, so listing them in the workspace's file sidebar
    # would drown out docs/notes. Accessible via the Repositories panel +
    # diff tabs instead.
    files = []

    # Cheap O(1) check against the in-memory tracker maintained by
    # routes/nb_exec.py. The previous file-scan implementation skipped
    # notebooks larger than 5 MB (e.g. Plotly-heavy notebooks easily clear
    # that), which left the sidebar dot dark for exactly the notebooks
    # users were most likely to want a "running" indicator on. The tracker
    # naturally clears on server restart — the Jupyter subprocess also dies
    # then, so the two stay consistent.
    from core.routes.nb_exec import is_path_pending as _ipynb_is_pending  # noqa: PLC0415

    def scan(dir_path, depth=0):
        if depth > _WORKSPACE_SCAN_MAX_DEPTH:
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
                rel = str(child.relative_to(workspace_path))
                ftype = "image" if child.suffix.lower() in IMAGE_EXTS else "file"
                entry = {"name": rel, "path": rel, "type": ftype}
                _with_symlink_fields(entry, child)
                # Every sidebar surface can optionally promote recently
                # updated files into a shortcut section. Keep mtime on every
                # file entry (not only notebooks) so that feature can filter
                # locally without another filesystem walk or endpoint.
                try:
                    entry["mtime"] = child.stat().st_mtime
                except OSError:
                    pass
                # Flag .ipynb files that currently have a running cell
                # so the sidebar can render a blinking activity dot
                # without each client polling every notebook. The common
                # mtime above also lets notebooks compare against a per-file
                # "last viewed" timestamp and show a new-results dot.
                if child.suffix.lower() == ".ipynb":
                    if _ipynb_is_pending(child):
                        entry["pending"] = True
                files.append(entry)
            elif child.is_dir():
                if child_is_symlink:
                    rel = str(child.relative_to(workspace_path))
                    entry = {"name": rel, "path": rel, "type": "dir"}
                    _with_symlink_fields(entry, child)
                    files.append(entry)
                if child.name not in _WORKSPACE_SCAN_SKIP_DIRS:
                    scan(child, _workspace_scan_child_depth(child, depth))
            elif child_is_symlink:
                # Broken symlink: still surface the row so the sidebar can
                # distinguish it from an absent file/folder.
                rel = str(child.relative_to(workspace_path))
                entry = {"name": rel, "path": rel, "type": "file", "broken": True}
                _with_symlink_fields(entry, child)
                files.append(entry)

    vault_root = auth.request_root(request)
    fsguard.guarded(vault_root, scan, workspace_path)
    return files


@router.get("/api/sidebar-worktrees")
def api_sidebar_worktrees(
    path: str,
    repo: str,
    request: Request,
    scope: str | None = None,
):
    """Return direct-child worktree scopes belonging to ``repo``.

    A shared worktree parent can contain checkouts from many repositories, so
    scanning every child directory leaks unrelated workspaces into the picker.
    Ask Git for the active repository's registered worktrees instead. A direct
    child may either be the checkout itself or a branch wrapper containing the
    checkout deeper below it. When ``repo`` points at a workspace nested inside a
    larger checkout, preserve that relative suffix for Git operations. An exact
    Git ``scope`` wins over stale registered-workspace metadata, and pasting a
    linked checkout as ``path`` is normalized to its containing folder.
    """
    try:
        parent = Path(path).expanduser().resolve()
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"Bad worktree folder: {exc}") from exc
    if not parent.is_dir():
        raise HTTPException(status_code=404, detail="Worktree folder not found")

    vault_root = auth.request_root(request)

    def repository_context() -> tuple[Path, Path, str]:
        """Choose a live checkout without letting stale workspace data win.

        ``scope`` is the visible workspace/folder root. Prefer it only when it
        has its own Git marker; otherwise a non-Git wrapper inside the Lab
        monorepo would accidentally resolve to the monorepo checkout instead
        of its registered nested repository.
        """
        candidates: list[tuple[str, bool]] = []
        if scope:
            candidates.append((scope, True))
        candidates.append((repo, False))
        saw_directory = False
        seen: set[str] = set()
        for raw, require_git_marker in candidates:
            try:
                candidate = Path(raw).expanduser().resolve()
            except OSError as exc:
                raise HTTPException(
                    status_code=400, detail=f"Bad repository root: {exc}",
                ) from exc
            key = str(candidate)
            if key in seen:
                continue
            seen.add(key)
            if not _git_status_dir_allowed(candidate, vault_root):
                raise HTTPException(status_code=403, detail="Repository is outside the vault")
            if not candidate.is_dir():
                continue
            saw_directory = True
            if require_git_marker and not (candidate / ".git").exists():
                continue
            try:
                git_root, relative_workspace = _entry_git_context(candidate, candidate)
            except HTTPException as exc:
                if exc.status_code == 404:
                    continue
                raise
            return candidate, git_root, relative_workspace
        if saw_directory:
            raise HTTPException(status_code=404, detail="This location is not in a Git repository")
        raise HTTPException(status_code=404, detail="Repository root not found")

    base_root, git_root, relative_workspace = repository_context()

    def list_worktrees() -> tuple[Path, list[dict[str, str]]]:
        try:
            proc = subprocess.run(
                ["git", "-C", str(git_root), "worktree", "list", "--porcelain"],
                capture_output=True,
                text=True,
                timeout=10,
            )
        except subprocess.TimeoutExpired as exc:
            raise HTTPException(status_code=504, detail="Git worktree lookup timed out") from exc
        if proc.returncode != 0:
            raise HTTPException(
                status_code=400,
                detail=proc.stderr.strip() or "Could not list Git worktrees",
            )

        worktree_roots: list[Path] = []
        for line in proc.stdout.splitlines():
            if not line.startswith("worktree "):
                continue
            try:
                worktree_roots.append(
                    Path(line.removeprefix("worktree ")).expanduser().resolve()
                )
            except OSError:
                continue

        # Git lists the primary checkout first. If the user pasted one linked
        # checkout rather than its containing folder, normalize the saved
        # setting to that checkout's parent and still include the checkout.
        primary_root = worktree_roots[0] if worktree_roots else git_root
        discovery_parent = parent
        if parent != primary_root and parent in worktree_roots:
            discovery_parent = parent.parent.resolve()

        suffix = Path(relative_workspace)
        rows: dict[str, dict[str, str]] = {}
        for worktree_root in worktree_roots:
            if worktree_root == primary_root:
                continue
            try:
                relative_worktree = worktree_root.relative_to(discovery_parent)
            except ValueError:
                continue
            if not relative_worktree.parts:
                continue
            scope_root = (discovery_parent / relative_worktree.parts[0]).resolve()
            if scope_root.name.startswith("."):
                continue
            candidate = (worktree_root / suffix).resolve()
            try:
                if candidate.is_dir():
                    scope_path = candidate if len(relative_worktree.parts) == 1 else scope_root
                    rows[str(scope_path)] = {
                        "name": scope_root.name,
                        "path": str(scope_path),
                        "repo": str(candidate),
                    }
            except OSError:
                continue
        return discovery_parent, sorted(
            rows.values(), key=lambda row: row["name"].casefold(),
        )

    resolved_parent, folders = fsguard.guarded(vault_root, list_worktrees)
    return {"path": str(resolved_parent), "repo": str(base_root), "folders": folders}


@router.get("/api/workspace-file")
def api_workspace_file(path: str, file: str):
    """Read a workspace-level file.

    Security: path-traversal is enforced on the *input* ``file`` parameter
    (no absolute paths, no ``..`` segments). We deliberately do NOT reject
    symlinks whose resolved target lives outside the workspace — the shared
    ``CLAUDE.md`` in every workspace is a symlink to
    ``content/skills/workspace-CLAUDE.md`` and we want it to read cleanly.
    """
    if file.startswith("/") or ".." in Path(file).parts:
        raise HTTPException(status_code=400, detail="Path traversal not allowed")
    workspace_path = Path(path).resolve()
    file_path = workspace_path / file  # no .resolve(): follow-through happens on I/O
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    try:
        content = file_path.read_text()
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="Binary file")
    return {"content": content, "name": file}


@router.get("/api/workspace-mtime")
def api_workspace_mtime(path: str, request: Request):
    """Return the latest mtime across files in a workspace directory.

    The client polls this every second from the workspace / self view to decide
    whether to refresh. The OLD implementation used ``rglob("*")`` with no
    skip-list and no depth cap, so on the self-view (``path = monorepo
    root``) it walked ``apps/*/.venv/``, ``repositories/``, and every
    cached site-packages tree — stalling the event loop for 20+ seconds
    every 2 seconds. That was the "reload takes forever" regression.

    Fix: mirror the same skip-list + dotfile skip + bounded depth the sibling
    ``/api/workspace-files`` already uses so the two endpoints agree on
    "what counts as part of the workspace". Nested Git checkouts receive a
    fresh depth budget. The general budget is also large enough for normal
    source trees even when nested Git metadata cannot be detected, while a
    hard cap still prevents an arbitrary directory chain from running away.
    On the self-view this drops the walk from ~25s to ~100ms.
    """
    workspace_path = Path(path)
    if not workspace_path.is_dir():
        # A missing directory is an expected steady state, not an error: a
        # browser tab can outlive its workspace (deleted, or on an unplugged
        # external volume) and keep polling for days — as a 404 each poll
        # logged a WARNING, thousands of pure noise lines. ``null`` tells
        # the client "nothing to compare against"; old clients treat it as
        # a harmless no-op (``null > x`` is false).
        return {"mtime": None}
    # Must stay in sync with api_workspace_files above — clients assume the
    # same tree shape (sidebar vs. mtime poll).
    latest = workspace_path.stat().st_mtime

    def scan(dir_path: Path, depth: int) -> None:
        nonlocal latest
        if depth > _WORKSPACE_SCAN_MAX_DEPTH:
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
                elif child.is_dir() and child.name not in _WORKSPACE_SCAN_SKIP_DIRS:
                    latest = max(latest, child.stat().st_mtime)
                    scan(child, _workspace_scan_child_depth(child, depth))
            except OSError:
                # Broken symlink / disappeared mid-walk — skip.
                continue

    vault_root = auth.request_root(request)
    fsguard.guarded(vault_root, scan, workspace_path, 0)
    return {"mtime": latest}


@router.get("/api/workspace-asset")
def api_workspace_asset(path: str, file: str):
    """Serve a static file (image, etc.) from a workspace directory. Same
    input-only traversal check as ``/api/workspace-file``."""
    if file.startswith("/") or ".." in Path(file).parts:
        raise HTTPException(status_code=400, detail="Path traversal not allowed")
    workspace_path = Path(path).resolve()
    file_path = workspace_path / file
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    media_type, _ = mimetypes.guess_type(str(file_path))
    return FileResponse(file_path, media_type=media_type)


class WorkspaceFileBody(BaseModel):
    path: str  # workspace path
    file: str  # file path relative to workspace
    content: str


@router.put("/api/workspace-file")
def update_workspace_file(body: WorkspaceFileBody):
    """Save a workspace-level file."""
    workspace_path = Path(body.path).resolve()
    file_path = (workspace_path / body.file).resolve()
    if not str(file_path).startswith(str(workspace_path)):
        raise HTTPException(status_code=400, detail="Path traversal not allowed")
    if not file_path.parent.is_dir():
        file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(body.content)
    return {"ok": True}


# ─── Workspace/vault explorer operations ─────────────────────────────

_ENTRY_NAME_RE = re.compile(r"^[^/\\\x00]+$")
_ENTRY_SHA_RE = re.compile(r"^[0-9a-fA-F]{4,40}$")
_ENTRY_WORKTREE_SHA = "WORKTREE"
_ENTRY_DIFF_MAX_BYTES = 8 * 1024 * 1024


def _entry_root(path: str, request: Request) -> Path:
    """Resolve an explorer root and keep it inside the authorized vault.

    The auth middleware scopes ``request_root`` from the absolute ``path`` in
    the query/body, including cross-vault tabs and the admin-only framework
    overview. This explicit containment check prevents an absolute-path API
    call from turning the explorer operations into a general filesystem API.
    """
    root = Path(path).expanduser().resolve()
    scoped_root = auth.request_root(request).expanduser().resolve()
    if root != scoped_root and scoped_root not in root.parents:
        raise HTTPException(status_code=403, detail="Path is outside the vault")
    if not root.is_dir():
        raise HTTPException(status_code=404, detail="Explorer root not found")
    return root


def _entry_target(root: Path, entry: str, *, allow_missing: bool = False) -> Path:
    """Resolve a relative explorer path without following its final symlink."""
    rel = Path(entry)
    if not entry or rel.is_absolute() or ".." in rel.parts or "" in rel.parts:
        raise HTTPException(status_code=400, detail="Invalid explorer path")
    target = root.joinpath(*rel.parts)
    # Resolve the parent so a symlinked directory cannot escape the root.
    parent = target.parent.resolve()
    if parent != root and root not in parent.parents:
        raise HTTPException(status_code=400, detail="Path escapes the explorer root")
    if not allow_missing and not (target.exists() or target.is_symlink()):
        raise HTTPException(status_code=404, detail="File or folder not found")
    return target


def _validate_entry_name(name: str) -> str:
    clean = name.strip()
    if clean in {"", ".", ".."} or not _ENTRY_NAME_RE.fullmatch(clean):
        raise HTTPException(status_code=400, detail="Name cannot contain a path separator")
    return clean


class WorkspaceEntryCreateBody(BaseModel):
    path: str
    parent: str = ""
    name: str
    kind: str = "file"


class WorkspaceEntryRenameBody(BaseModel):
    path: str
    entry: str
    new_name: str


class WorkspaceEntryDeleteBody(BaseModel):
    path: str
    entry: str


def _new_notebook_document() -> dict:
    """Return a valid, empty notebook for repository-first creation."""
    return {
        "cells": [],
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3 (Lab)",
                "language": "python",
                "name": "python3",
            },
            "language_info": {"name": "python"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


@router.post("/api/workspace-entry")
def create_workspace_entry(body: WorkspaceEntryCreateBody, request: Request):
    root = _entry_root(body.path, request)
    name = _validate_entry_name(body.name)
    if body.kind not in {"file", "folder", "notebook"}:
        raise HTTPException(status_code=400, detail="Kind must be file, folder, or notebook")
    if body.kind == "notebook" and not name.lower().endswith(".ipynb"):
        name = _validate_entry_name(f"{name}.ipynb")
    if body.parent:
        parent = _entry_target(root, body.parent)
        if not parent.is_dir():
            raise HTTPException(status_code=400, detail="Parent is not a folder")
    else:
        parent = root
    target = parent / name
    if target.exists() or target.is_symlink():
        raise HTTPException(status_code=409, detail="A file or folder with that name already exists")

    def _create() -> None:
        if body.kind == "folder":
            target.mkdir()
        elif body.kind == "notebook":
            target.write_text(
                json.dumps(_new_notebook_document(), indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        else:
            target.touch(exist_ok=False)

    fsguard.guarded(root, _create)
    return {"ok": True, "entry": str(target.relative_to(root)), "kind": body.kind}


@router.patch("/api/workspace-entry")
def rename_workspace_entry(body: WorkspaceEntryRenameBody, request: Request):
    root = _entry_root(body.path, request)
    target = _entry_target(root, body.entry)
    new_name = _validate_entry_name(body.new_name)
    destination = target.with_name(new_name)
    if destination.exists() or destination.is_symlink():
        raise HTTPException(status_code=409, detail="A file or folder with that name already exists")
    fsguard.guarded(root, target.rename, destination)
    return {
        "ok": True,
        "entry": str(target.relative_to(root)),
        "renamed_to": str(destination.relative_to(root)),
    }


@router.delete("/api/workspace-entry")
def delete_workspace_entry(body: WorkspaceEntryDeleteBody, request: Request):
    root = _entry_root(body.path, request)
    target = _entry_target(root, body.entry)

    def _delete() -> None:
        # A directory symlink must delete the link itself, never its target.
        if target.is_symlink() or target.is_file():
            target.unlink()
        elif target.is_dir():
            shutil.rmtree(target)
        else:
            raise HTTPException(status_code=404, detail="File or folder not found")

    fsguard.guarded(root, _delete)
    return {"ok": True, "entry": body.entry}


def _entry_git_context(root: Path, target: Path) -> tuple[Path, str]:
    # Discover Git from the selected entry, not the explorer root. A workspace can
    # contain another repository, and Git must choose the nearest enclosing
    # worktree exactly as it would when invoked beside the selected file.
    git_cwd = target if target.is_dir() else target.parent
    try:
        proc = subprocess.run(
            ["git", "-C", str(git_cwd), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise HTTPException(status_code=404, detail="This location is not in a Git repository")
    if proc.returncode != 0:
        raise HTTPException(status_code=404, detail="This location is not in a Git repository")
    repo_root = Path(proc.stdout.strip()).resolve()
    try:
        repo_rel = str(target.relative_to(repo_root))
    except ValueError:
        raise HTTPException(status_code=400, detail="File is outside the Git repository")
    return repo_root, repo_rel


def _entry_untracked_files(repo_root: Path, repo_rel: str) -> list[str]:
    try:
        proc = subprocess.run(
            [
                "git", "-C", str(repo_root), "ls-files", "--others",
                "--exclude-standard", "-z", "--", repo_rel,
            ],
            capture_output=True, timeout=10,
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Git status timed out")
    if proc.returncode != 0:
        detail = proc.stderr.decode(errors="replace").strip()
        raise HTTPException(status_code=400, detail=detail or "Could not read Git status")
    return [item.decode(errors="replace") for item in proc.stdout.split(b"\0") if item]


def _entry_has_head(repo_root: Path) -> bool:
    try:
        return subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "--verify", "HEAD"],
            capture_output=True, text=True, timeout=5,
        ).returncode == 0
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Git commit lookup timed out")


def _entry_worktree_diff(repo_root: Path, repo_rel: str) -> tuple[str, list[str]]:
    """Return the final HEAD-to-working-tree patch, including untracked files."""
    untracked = _entry_untracked_files(repo_root, repo_rel)
    files_from_empty = untracked
    try:
        has_head = _entry_has_head(repo_root)
        if has_head:
            tracked = subprocess.run(
                [
                    "git", "-C", str(repo_root), "diff", "HEAD", "--no-color",
                    "--find-renames", "--", repo_rel,
                ],
                capture_output=True, text=True, timeout=20,
            )
            if tracked.returncode != 0:
                raise HTTPException(
                    status_code=400,
                    detail=tracked.stderr.strip() or "Could not read uncommitted changes",
                )
            patches = [tracked.stdout]
        else:
            # In an unborn repository every indexed file is also uncommitted.
            indexed = subprocess.run(
                ["git", "-C", str(repo_root), "ls-files", "-z", "--", repo_rel],
                capture_output=True, timeout=10,
            )
            if indexed.returncode != 0:
                detail = indexed.stderr.decode(errors="replace").strip()
                raise HTTPException(status_code=400, detail=detail or "Could not read Git index")
            tracked_files = [
                item.decode(errors="replace")
                for item in indexed.stdout.split(b"\0") if item
            ]
            patches = []
            files_from_empty = list(dict.fromkeys(tracked_files + untracked))

        for untracked_file in files_from_empty:
            created = subprocess.run(
                [
                    "git", "-C", str(repo_root), "diff", "--no-index",
                    "--no-color", "--", "/dev/null", untracked_file,
                ],
                capture_output=True, text=True, timeout=20,
            )
            # git diff --no-index returns 1 when differences were found.
            if created.returncode not in {0, 1}:
                raise HTTPException(
                    status_code=400,
                    detail=created.stderr.strip() or "Could not read untracked file diff",
                )
            patches.append(created.stdout)

        states = []
        staged = subprocess.run(
            ["git", "-C", str(repo_root), "diff", "--cached", "--quiet", "--", repo_rel],
            timeout=10,
        )
        unstaged = subprocess.run(
            ["git", "-C", str(repo_root), "diff", "--quiet", "--", repo_rel],
            timeout=10,
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Git diff timed out")

    if staged.returncode == 1:
        states.append("staged")
    if unstaged.returncode == 1:
        states.append("unstaged")
    if untracked:
        states.append("untracked")
    return "".join(patches), states


def _entry_git_blob(repo_root: Path, revision: str, repo_rel: str) -> str:
    """Read a text blob from Git; a missing path/revision is an empty side."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), "show", f"{revision}:{repo_rel}"],
            capture_output=True, text=True, timeout=20,
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Git notebook history timed out")
    if proc.returncode != 0:
        return ""
    if len(proc.stdout.encode(errors="replace")) > _ENTRY_DIFF_MAX_BYTES:
        raise HTTPException(status_code=413, detail="Notebook revision is too large to render")
    return proc.stdout


def _entry_notebook_history_diff(
    root: Path,
    target: Path,
    repo_root: Path,
    repo_rel: str,
    file: str,
    sha: str,
) -> dict:
    if sha == _ENTRY_WORKTREE_SHA:
        _, states = _entry_worktree_diff(repo_root, repo_rel)
        before_raw = _entry_git_blob(repo_root, "HEAD", repo_rel)
        try:
            size = target.stat().st_size
        except OSError:
            size = 0
        if size > _ENTRY_DIFF_MAX_BYTES:
            raise HTTPException(status_code=413, detail="Notebook is too large to render")
        after_raw = fsguard.guarded(root, target.read_text, errors="replace")
        kind = "working-tree"
    else:
        try:
            verified = subprocess.run(
                ["git", "-C", str(repo_root), "cat-file", "-e", f"{sha}^{{commit}}"],
                capture_output=True, text=True, timeout=10,
            )
        except subprocess.TimeoutExpired:
            raise HTTPException(status_code=504, detail="Git commit lookup timed out")
        if verified.returncode != 0:
            raise HTTPException(status_code=404, detail="Commit not found")
        before_raw = _entry_git_blob(repo_root, f"{sha}^", repo_rel)
        after_raw = _entry_git_blob(repo_root, sha, repo_rel)
        states = []
        kind = "commit"

    notebook = diff_notebook_cells(
        parse_notebook_content(before_raw),
        parse_notebook_content(after_raw),
    )
    return {
        "file": file,
        "sha": sha,
        "kind": kind,
        "states": states,
        "notebook": notebook,
    }


def _entry_history_revision_files(
    repo_root: Path,
    repo_rel: str,
    sha: str,
) -> tuple[list[dict], list[str]]:
    """Return every file changed by a history revision, selected path first."""
    if sha == _ENTRY_WORKTREE_SHA:
        patch, _ = _entry_worktree_diff(repo_root, ".")
    else:
        try:
            proc = subprocess.run(
                [
                    "git", "-C", str(repo_root), "show", "--format=",
                    "--no-color", "--find-renames", sha,
                ],
                capture_output=True, text=True, timeout=20,
            )
        except subprocess.TimeoutExpired:
            raise HTTPException(status_code=504, detail="Git diff timed out")
        if proc.returncode != 0:
            raise HTTPException(
                status_code=404,
                detail=proc.stderr.strip() or "Commit not found",
            )
        patch = proc.stdout

    files = parse_unified_diff(patch)
    selected = repo_rel.rstrip("/")

    def selected_rank(item: dict) -> int:
        filename = str(item.get("filename", "")).rstrip("/")
        if filename == selected:
            return 0
        if selected and filename.startswith(selected + "/"):
            return 1
        return 2

    # Python's stable sort preserves Git's original order inside each group.
    files.sort(key=selected_rank)
    return files, [str(item.get("filename", "")) for item in files]


@router.get("/api/workspace-entry/history")
def workspace_entry_history(
    path: str,
    file: str,
    request: Request,
    limit: int = 50,
):
    root = _entry_root(path, request)
    target = _entry_target(root, file)
    repo_root, repo_rel = _entry_git_context(root, target)
    limit = max(1, min(limit, 200))
    args = [
        "git", "-C", str(repo_root), "log", f"--max-count={limit}",
        "--format=%H%x1f%h%x1f%an%x1f%ae%x1f%aI%x1f%ar%x1f%s%x1e",
    ]
    if target.is_file() or target.is_symlink():
        args.append("--follow")
    args.extend(["--", repo_rel])
    commits = []
    # ``git log`` exits 128 before the repository's first commit. That is a
    # valid history state: indexed/untracked files still need a WORKTREE row
    # and diff, so skip the commit lookup while HEAD is unborn.
    if _entry_has_head(repo_root):
        try:
            proc = subprocess.run(args, capture_output=True, text=True, timeout=15)
        except subprocess.TimeoutExpired:
            raise HTTPException(status_code=504, detail="Git history timed out")
        if proc.returncode != 0:
            raise HTTPException(status_code=400, detail=proc.stderr.strip() or "Could not read Git history")
        for record in proc.stdout.split("\x1e"):
            parts = record.strip().split("\x1f", 6)
            if len(parts) != 7:
                continue
            sha, short_sha, author, email, date_iso, relative_date, message = parts
            commits.append({
                "sha": sha,
                "short_sha": short_sha,
                "author": author,
                "email": email,
                "date": date_iso,
                "relative_date": relative_date,
                "message": message,
            })
    working_patch, working_states = _entry_worktree_diff(repo_root, repo_rel)
    if working_patch:
        commits.insert(0, {
            "sha": _ENTRY_WORKTREE_SHA,
            "short_sha": "uncommitted",
            "author": "Working tree",
            "email": "",
            "date": "",
            "relative_date": "now",
            "message": "Uncommitted changes",
            "kind": "working-tree",
            "states": working_states,
        })
    return {
        "file": file,
        "repo": str(repo_root),
        "repo_file": repo_rel,
        "commits": commits,
    }


@router.get("/api/workspace-entry/history-diff")
def workspace_entry_history_diff(path: str, file: str, sha: str, request: Request):
    if sha != _ENTRY_WORKTREE_SHA and not _ENTRY_SHA_RE.fullmatch(sha):
        raise HTTPException(status_code=400, detail="Invalid commit")
    root = _entry_root(path, request)
    target = _entry_target(root, file)
    repo_root, repo_rel = _entry_git_context(root, target)
    files, changed_files = _entry_history_revision_files(repo_root, repo_rel, sha)
    if repo_rel.lower().endswith(".ipynb"):
        result = _entry_notebook_history_diff(
            root, target, repo_root, repo_rel, file, sha,
        )
        result.update({
            "repo": str(repo_root),
            "selected_file": repo_rel,
            "changed_files": changed_files,
            "files": files,
        })
        return result
    if sha == _ENTRY_WORKTREE_SHA:
        _, states = _entry_worktree_diff(repo_root, repo_rel)
        return {
            "file": file,
            "repo": str(repo_root),
            "selected_file": repo_rel,
            "sha": sha,
            "kind": "working-tree",
            "states": states,
            "changed_files": changed_files,
            "files": files,
        }
    return {
        "file": file,
        "repo": str(repo_root),
        "selected_file": repo_rel,
        "sha": sha,
        "changed_files": changed_files,
        "files": files,
    }


@router.get("/api/workspace-diff-file")
def workspace_diff_file(path: str, file: str, request: Request):
    root = _entry_root(path, request)
    target = _entry_target(root, file)
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Diff file not found")
    try:
        size = target.stat().st_size
    except OSError:
        size = 0
    if size > _ENTRY_DIFF_MAX_BYTES:
        raise HTTPException(status_code=413, detail="Diff file is too large to render")
    try:
        raw = fsguard.guarded(root, target.read_text, errors="replace")
    except OSError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"file": file, "files": parse_unified_diff(raw), "raw": raw}


@router.get("/api/workspace-comments")
def api_workspace_comments(path: str):
    """Read comments.json from workspace."""
    comments_path = Path(path) / "comments.json"
    if not comments_path.is_file():
        return []
    try:
        return json.loads(comments_path.read_text())
    except (json.JSONDecodeError, ValueError):
        return []


class CommentBody(BaseModel):
    path: str            # workspace path (holds comments.json)
    file: str            # file the comment is on
    text: str            # selected text (doc) or line content (code)
    comment: str         # the user's note
    # Optional context for code/diff comments — all default to None so doc
    # comments continue to round-trip unchanged.
    kind: str | None = None        # 'doc' (default when absent) | 'code'
    repo: str | None = None        # relative repo/worktree path within the workspace
    scope: str | None = None       # 'uncommitted' | 'branch' | 'commit'
    sha: str | None = None         # commit SHA (only when scope='commit')
    line: int | None = None        # line number the comment targets
    side: str | None = None        # 'old' | 'new' (which side of the diff)


@router.post("/api/workspace-comments")
def add_workspace_comment(body: CommentBody):
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


@router.delete("/api/workspace-comments")
def delete_workspace_comment(body: CommentDeleteBody):
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


@router.post("/api/workspace-action-complete")
def complete_workspace_action(body: ActionCompleteBody):
    """Mark an action/task item as done with optional artifacts.

    Writes back to the new ``tasks.json`` schema when present; falls back
    to the legacy ``actions.json`` array for older workspaces.
    """
    import datetime

    workspace_path = _resolve_workspace_path(body.path)

    tasks_path = workspace_path / "tasks.json"
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

    actions_path = workspace_path / "actions.json"
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
