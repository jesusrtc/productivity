from __future__ import annotations

import json
import os
import re
import tomllib
from pathlib import Path
from typing import Any


class MonorepoNotFound(RuntimeError):
    """Raised when the monorepo root cannot be located."""


def global_config_dir() -> Path:
    """Return Lab's user-level config directory.

    This directory stores only framework-level config, such as the workspace
    registry. Workspace data, caches, indexes, sessions, and logs stay under
    the active workspace.
    """
    return Path(os.environ.get("LAB_HOME", "~/.lab")).expanduser()


def workspaces_file() -> Path:
    return global_config_dir() / "workspaces.toml"


def local_cli_token_file() -> Path:
    """Return the owner-readable bearer token shared by Lab and its CLI."""
    return global_config_dir() / "local-cli-token"


def read_local_cli_token() -> str | None:
    """Read the local CLI bearer token without creating or rotating it."""
    target = local_cli_token_file()
    try:
        token = target.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if len(token) < 32 or any(char.isspace() for char in token):
        return None
    return token


def toml_str(value: str) -> str:
    # TOML basic strings accept JSON-style escaping for this subset.
    return json.dumps(value)


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9_-]+", "-", value.strip().lower()).strip("-")
    return slug or "workspace"


def read_workspace_registry() -> dict[str, Any]:
    path = workspaces_file()
    if not path.is_file():
        return {"active": None, "workspaces": []}
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    workspaces = data.get("workspaces") or []
    if not isinstance(workspaces, list):
        workspaces = []
    rows: list[dict[str, str]] = []
    for row in workspaces:
        if not isinstance(row, dict):
            continue
        path_value = row.get("path")
        if not isinstance(path_value, str) or not path_value:
            continue
        wid = row.get("id")
        name = row.get("name")
        rows.append({
            "id": str(wid or _slug(Path(path_value).name)),
            "name": str(name or Path(path_value).name),
            "path": path_value,
        })
    active = data.get("active")
    return {"active": active if isinstance(active, str) else None, "workspaces": rows}


def write_workspace_registry(data: dict[str, Any]) -> Path:
    rows = list(data.get("workspaces") or [])
    active = data.get("active")
    lines: list[str] = []
    if active:
        lines.append(f"active = {toml_str(str(active))}")
        lines.append("")
    for row in rows:
        lines.append("[[workspaces]]")
        lines.append(f"id = {toml_str(str(row['id']))}")
        lines.append(f"name = {toml_str(str(row['name']))}")
        lines.append(f"path = {toml_str(str(Path(row['path']).expanduser().resolve()))}")
        lines.append("")
    path = workspaces_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return path


def register_workspace(root: Path, *, name: str | None = None,
                       workspace_id: str | None = None,
                       active: bool = True) -> dict[str, str]:
    """Add or update a workspace in the global registry."""
    resolved = root.expanduser().resolve()
    data = read_workspace_registry()
    rows = list(data.get("workspaces") or [])
    existing_ids = {str(row.get("id")) for row in rows}
    existing = next((row for row in rows
                     if Path(str(row.get("path", ""))).expanduser().resolve() == resolved), None)
    if existing:
        row = existing
        if name:
            row["name"] = name
    else:
        base_id = _slug(workspace_id or name or resolved.name)
        wid = base_id
        i = 2
        while wid in existing_ids:
            wid = f"{base_id}-{i}"
            i += 1
        row = {"id": wid, "name": name or resolved.name, "path": str(resolved)}
        rows.append(row)
    data["workspaces"] = rows
    if active:
        data["active"] = row["id"]
    write_workspace_registry(data)
    return {"id": str(row["id"]), "name": str(row["name"]), "path": str(row["path"])}


def active_workspace() -> Path | None:
    data = read_workspace_registry()
    active = data.get("active")
    if not active:
        return None
    for row in data.get("workspaces") or []:
        if row.get("id") == active:
            return Path(str(row["path"])).expanduser().resolve()
    return None


def _looks_like_framework_checkout(candidate: Path) -> bool:
    if not ((candidate / "Makefile").is_file() and (candidate / "core").is_dir()):
        return False
    if (candidate / "core" / "cli" / "src" / "lab").is_dir():
        return True
    # Older checkouts kept the CLI under apps/lab.
    if (
        (candidate / "apps" / "lab").is_dir()
        and (candidate / "core" / "src" / "core").is_dir()
    ):
        return True
    return False


def _looks_like_workspace(candidate: Path) -> bool:
    if (candidate / "lab.toml").is_file():
        return True
    if _looks_like_framework_checkout(candidate):
        return False
    # Compatibility with the current productivity repo before `lab init`.
    return (candidate / ".git").exists() and (candidate / "content").is_dir()


def find_workspace_root(start: Path | None = None, *, use_registry: bool = True) -> Path:
    """Locate the active Lab workspace.

    Resolution order:
      1. `LAB_WORKSPACE` environment variable.
      2. `LAB_ROOT` compatibility environment variable.
      3. Walk up from `start` (defaults to PWD) until a workspace marker is found.
      4. Active entry in `~/.lab/workspaces.toml`.

    Raises `MonorepoNotFound` if neither resolves.
    """
    env_workspace = os.environ.get("LAB_WORKSPACE")
    if env_workspace:
        return Path(env_workspace).expanduser().resolve()

    env_root = os.environ.get("LAB_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()

    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if _looks_like_workspace(candidate):
            return candidate
    if use_registry:
        active = active_workspace()
        if active is not None:
            return active
    raise MonorepoNotFound(
        f"No Lab workspace found from {current}. Set LAB_WORKSPACE or run `lab init`."
    )


def find_monorepo_root(start: Path | None = None) -> Path:
    """Compatibility wrapper for older code that still says monorepo."""
    return find_workspace_root(start)


def find_framework_root(start: Path | None = None) -> Path:
    """Locate the framework source checkout used by `make install/start`.

    In the editable install path this walks up from the installed package file.
    `LAB_FRAMEWORK_ROOT` can override it for tests or unusual installs.
    """
    env_root = os.environ.get("LAB_FRAMEWORK_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()

    current = (start or Path(__file__)).resolve()
    for candidate in (current, *current.parents):
        if _looks_like_framework_checkout(candidate):
            return candidate
    raise MonorepoNotFound(
        "No Lab framework checkout found. Set LAB_FRAMEWORK_ROOT or reinstall from source."
    )


def workspace_state_dir(root: Path) -> Path:
    return root / ".lab" / "state"


def logs_dir(root: Path) -> Path:
    return workspace_state_dir(root) / "logs"


def port_file(root: Path) -> Path:
    return workspace_state_dir(root) / "server.port"


def configured_server_port(root: Path, default: int = 3333) -> int:
    """Return ``[server].port`` from the workspace's ``lab.toml``.

    Runtime overrides and the live ``.lab/state/server.port`` file are handled
    by callers. This helper only resolves the workspace's persistent default.
    """
    config = root.expanduser().resolve() / "lab.toml"
    if not config.is_file():
        return default
    try:
        data = tomllib.loads(config.read_text(encoding="utf-8"))
        value = (data.get("server") or {}).get("port")
    except (OSError, tomllib.TOMLDecodeError, AttributeError):
        return default
    if isinstance(value, bool) or not isinstance(value, int):
        return default
    return value if 1 <= value <= 65535 else default


def client_env_value(framework_root: Path, wanted_key: str) -> str | None:
    """Return one literal value from the client checkout's local ``.env``.

    This intentionally parses only simple ``KEY=value`` lines.  Lab's client
    file is configuration, not a shell script, so values are never executed or
    expanded.  ``LAB_ENV_FILE`` keeps tests and unusual installations able to
    point at a different file.
    """
    path = client_env_file(framework_root)
    if not path.is_file():
        return None
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, separator, value = line.partition("=")
        if separator != "=" or key.strip() != wanted_key:
            continue
        text = value.strip()
        if len(text) >= 2 and text[0] == text[-1] and text[0] in ("'", '"'):
            text = text[1:-1]
        return text or None
    return None


def client_env_file(framework_root: Path) -> Path:
    """Return the local client configuration file used by Lab."""
    configured_path = os.environ.get("LAB_ENV_FILE")
    return (Path(configured_path).expanduser() if configured_path
            else framework_root.expanduser().resolve() / ".env")


def set_client_env_value(framework_root: Path, key: str, value: str) -> Path:
    """Persist one literal value in the client checkout's local ``.env``.

    Existing comments, blank lines, and unrelated settings are preserved. A
    JSON string is valid dotenv syntax for paths and safely quotes whitespace.
    """
    if not re.fullmatch(r"[A-Z][A-Z0-9_]*", key):
        raise ValueError("client environment key must use uppercase letters, digits, and underscores")
    path = client_env_file(framework_root)
    try:
        lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
        existing_mode = path.stat().st_mode & 0o777 if path.is_file() else None
    except OSError as exc:
        raise ValueError(f"could not read client configuration: {exc}") from exc
    replacement = f"{key}={json.dumps(value)}"
    updated: list[str] = []
    replaced = False
    for raw in lines:
        candidate = raw.strip()
        if candidate.startswith("export "):
            candidate = candidate[7:].lstrip()
        found_key, separator, _found_value = candidate.partition("=")
        if separator == "=" and found_key.strip() == key:
            if not replaced:
                updated.append(replacement)
                replaced = True
            continue
        updated.append(raw)
    if not replaced:
        if updated and updated[-1]:
            updated.append("")
        updated.append(replacement)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text("\n".join(updated).rstrip() + "\n", encoding="utf-8")
        if existing_mode is not None:
            temporary.chmod(existing_mode)
        temporary.replace(path)
    except OSError as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise ValueError(f"could not save client configuration: {exc}") from exc
    return path


def client_env_server_port(framework_root: Path) -> int | None:
    """Return ``LAB_PORT`` from the client checkout's local ``.env`` file."""
    text = client_env_value(framework_root, "LAB_PORT")
    if text is None:
        return None
    try:
        port = int(text)
    except ValueError:
        return None
    return port if 1 <= port <= 65535 else None


def assistant_root(framework_root: Path | None = None) -> Path | None:
    """Return the client-owned global Assistant database directory.

    ``LAB_ASSISTANT_HOME`` is a one-run override.  Otherwise the path is read
    from the framework checkout's uncommitted ``.env``.  There is deliberately
    no workspace fallback: one client has one Assistant database regardless of
    which workspace is active.
    """
    raw = os.environ.get("LAB_ASSISTANT_HOME")
    if not raw:
        try:
            framework = framework_root or find_framework_root()
        except MonorepoNotFound:
            return None
        raw = client_env_value(framework, "LAB_ASSISTANT_HOME")
    if not raw:
        return None
    return Path(raw).expanduser().resolve()


def sessions_file(root: Path) -> Path:
    return workspace_state_dir(root) / "sessions" / "sessions.json"


def ui_state_file(root: Path) -> Path:
    return workspace_state_dir(root) / "ui-state.json"


# Pseudo-project id for the Lab framework checkout itself. Like __cerebro__,
# it has no folder under projects/ — its meta + tasks live in
# hidden files under content/ so they don't clutter the project listing.
SELF_PROJECT_ID = "__self__"


def is_pseudo_project(project_id: str) -> bool:
    """True for ids that aren't backed by projects/<id>/."""
    return project_id == SELF_PROJECT_ID


def project_dir(root: Path, project_id: str) -> Path:
    # Pseudo-projects don't have a directory of their own; return the
    # content root so callers that only use this for relative paths
    # (notes_file creation, etc.) have a sensible base. Callers that need
    # a real project folder should check is_pseudo_project() first.
    if is_pseudo_project(project_id):
        return root / "content"
    return root / "projects" / project_id


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
            "description": "The Lab framework checkout itself — commits, uncommitted changes, and repo-level tasks.",
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
    """Raised when PWD is not inside any project under projects/."""


def find_project_id_from_pwd(root: Path, start: Path | None = None) -> str:
    """Walk up from `start` (defaults to PWD) to find the project folder.

    Returns the project id (the directory name whose parent is
    `<root>/projects/`). Raises `ProjectNotFound` if the walk
    reaches `root` without finding a project folder.
    """
    projects_root = (root / "projects").resolve()
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
    """Return the path of the workspace-local index cache."""
    return workspace_state_dir(root) / "indexes" / "index.json"


def legacy_index_file(root: Path) -> Path:
    return root / "content" / ".index.json"


# ─── Cross-tool agent config + memory ────────────────────────────────────────
# `.agents/` is the committed home shared by Claude Code, Codex and Copilot for
# config + memory. It is distinct from `.claude/agents/` (Claude subagents).

def agents_dir(root: Path) -> Path:
    """Cross-tool agent home (committed to the productivity repo)."""
    return root / ".agents"


def config_file(root: Path) -> Path:
    """Global lab/agent settings file (defaultAgent, model, theme)."""
    return agents_dir(root) / "config.json"


def memory_dir(root: Path, project_id: str | None = None) -> Path:
    """Canonical, repo-committed agent memory directory.

    Monorepo-level memory lives at ``<root>/.agents/memory/`` (productivity
    repo). Per-project memory lives at ``projects/<id>/.agents/memory/``
    (committed to the content repo, so it travels with project work).
    """
    if project_id and not is_pseudo_project(project_id):
        return project_dir(root, project_id) / ".agents" / "memory"
    return agents_dir(root) / "memory"


def claude_project_slug(path: Path) -> str:
    """Claude Code's ``~/.claude/projects/<slug>`` name for an absolute path.

    Claude derives the slug by replacing every path separator with ``-`` (e.g.
    ``/Volumes/SSD/.../productivity`` → ``-Volumes-SSD-...-productivity``).
    """
    return str(Path(path).resolve()).replace("/", "-")


def claude_memory_dir(path: Path) -> Path:
    """The built-in ``~/.claude`` memory dir for a project rooted at ``path``."""
    return Path.home() / ".claude" / "projects" / claude_project_slug(path) / "memory"
