from __future__ import annotations

import os
from pathlib import Path


class MonorepoNotFound(RuntimeError):
    """Raised when the monorepo root cannot be located."""


def find_monorepo_root(start: Path | None = None) -> Path:
    """Locate the monorepo root.

    Resolution order:
      1. `LAB_ROOT` environment variable (absolute path).
      2. Walk up from `start` (defaults to PWD) until a directory containing
         both `.git` and `content/` is found.

    Raises `MonorepoNotFound` if neither resolves.
    """
    env_root = os.environ.get("LAB_ROOT")
    if env_root:
        return Path(env_root)

    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists() and (candidate / "content").is_dir():
            return candidate
    raise MonorepoNotFound(
        f"No monorepo found from {current}. Set LAB_ROOT or run inside the repo."
    )


# Pseudo-project id for the productivity monorepo itself. Like __cerebro__,
# it has no folder under content/projects/ — its meta + tasks live in
# hidden files under content/ so they don't clutter the project listing.
SELF_PROJECT_ID = "__self__"


def is_pseudo_project(project_id: str) -> bool:
    """True for ids that aren't backed by content/projects/<id>/."""
    return project_id == SELF_PROJECT_ID


def project_dir(root: Path, project_id: str) -> Path:
    # Pseudo-projects don't have a directory of their own; return the
    # content root so callers that only use this for relative paths
    # (notes_file creation, etc.) have a sensible base. Callers that need
    # a real project folder should check is_pseudo_project() first.
    if is_pseudo_project(project_id):
        return root / "content"
    return root / "content" / "projects" / project_id


def project_file(root: Path, project_id: str) -> Path:
    if project_id == SELF_PROJECT_ID:
        return root / "content" / ".self-project.json"
    return project_dir(root, project_id) / "project.json"


def tasks_file(root: Path, project_id: str) -> Path:
    if project_id == SELF_PROJECT_ID:
        return root / "content" / ".self-tasks.json"
    return project_dir(root, project_id) / "tasks.json"


def ensure_self_files(root: Path) -> None:
    """Bootstrap empty meta + tasks files for the productivity pseudo-project.

    Idempotent. Safe to call on every read/write of __self__ state.
    """
    pjson = project_file(root, SELF_PROJECT_ID)
    tjson = tasks_file(root, SELF_PROJECT_ID)
    pjson.parent.mkdir(parents=True, exist_ok=True)
    if not pjson.is_file():
        import json as _json
        today = __import__("datetime").date.today().isoformat()
        pjson.write_text(_json.dumps({
            "id": SELF_PROJECT_ID,
            "name": "Productivity",
            "description": "The productivity monorepo itself — commits, uncommitted changes, and repo-level tasks.",
            "status": "active",
            "tags": [],
            "labels": [],
            "priority": None,
            "loe": None,
            "due": None,
            "created": today,
            "updated": today,
            "worktrees": [],
            "prs": [],
            "artifacts": [],
            "pinned": [],
            "hold": None,
        }, indent=2) + "\n")
    if not tjson.is_file():
        import json as _json
        tjson.write_text(_json.dumps({"next_id": 1, "tasks": []}, indent=2) + "\n")


class ProjectNotFound(RuntimeError):
    """Raised when PWD is not inside any project under content/projects/."""


def find_project_id_from_pwd(root: Path, start: Path | None = None) -> str:
    """Walk up from `start` (defaults to PWD) to find the project folder.

    Returns the project id (the directory name whose parent is
    `<root>/content/projects/`). Raises `ProjectNotFound` if the walk
    reaches `root` without finding a project folder.
    """
    projects_root = (root / "content" / "projects").resolve()
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if candidate.parent == projects_root:
            return candidate.name
        if candidate == root.resolve():
            break
    raise ProjectNotFound(
        "no project — pass --project <id> or cd into a project folder"
    )


def index_file(root: Path) -> Path:
    """Return the path of the global index cache (gitignored)."""
    return root / "content" / ".index.json"
