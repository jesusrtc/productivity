"""Workspace locations and terminal identities, independent of display names.

The workspace ID remains an API key. Its folder may move; the location index
is rebuildable from workspace.json. Session UUIDs are durable, unlike the
live tmux registry, and never change when a workspace or tab is renamed.
"""
from __future__ import annotations

import fcntl
import json
import os
import re
import subprocess
import unicodedata
import uuid
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from functools import lru_cache
from urllib.parse import quote

from lab import naming, storage


def _state(root: Path) -> Path:
    from lab import paths
    return paths.vault_state_dir(root)


@contextmanager
def identity_lock(root: Path):
    lock = _state(root) / "identity.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open("a+") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def operation_lease(root: Path, workspace_id: str, *, exclusive: bool = False):
    """Nonblocking lease: a folder cannot move while a notebook writes to it."""
    key = uuid.uuid5(uuid.NAMESPACE_URL, workspace_id).hex
    lock = _state(root) / "workspace-locks" / (key + ".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    handle = lock.open("a+")
    try:
        fcntl.flock(handle.fileno(), (fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH) | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        raise ValueError("Workspace is busy; wait for active operations to finish") from None
    return handle


@contextmanager
def workspace_operation(root: Path, workspace_id: str):
    with operation_lease(root, workspace_id, exclusive=True):
        yield


@lru_cache(maxsize=256)
def _read_version(path: Path, signature: tuple) -> dict:
    value = storage.read_json(path)
    return value if isinstance(value, dict) else {}


def _read(path: Path) -> dict:
    try:
        stat = path.stat()
        return _read_version(path, (stat.st_ino, stat.st_mtime_ns, stat.st_size)).copy()
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def slug(name: str) -> str:
    normalized = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9_-]+", "-", normalized).strip("-_") or "workspace"


def id_at(folder: Path) -> str:
    return str(_read(naming.workspace_metadata_file(folder)).get("id") or folder.name)


def folder_for(root: Path, workspace_id: str) -> Path:
    """Resolve an ID without depending on its original directory name."""
    base = naming.workspaces_dir(root)
    index = _read(_state(root) / "workspace-locations.json")
    folder = index.get(workspace_id)
    if isinstance(folder, str) and folder and Path(folder).name == folder:
        candidate = base / folder
        if candidate.is_dir() and id_at(candidate) == workspace_id:
            return candidate
    direct = base / workspace_id
    if direct.exists() or not base.is_dir():
        return direct
    # Recovery after losing the location cache. The ID lives in the moved
    # workspace's metadata, so it remains resolvable without that cache.
    for child in base.iterdir():
        if child.is_dir() and naming.workspace_metadata_file(child).is_file() and id_at(child) == workspace_id:
            return child
    return direct


def rebase(value, old: Path, new: Path, root: Path):
    """Rebase complete path values only; never rewrite prose or shell code."""
    pairs = [(str(old), str(new)), (old.relative_to(root).as_posix(), new.relative_to(root).as_posix())]
    if isinstance(value, str):
        encoded_old, encoded_new = quote(str(old), safe=""), quote(str(new), safe="")
        if value == encoded_old or value.startswith(encoded_old + "%2F"):
            return encoded_new + value[len(encoded_old):]
        for before, after in pairs:
            if value == before or value.startswith(before + "/"):
                return after + value[len(before):]
        return value
    if isinstance(value, list):
        return [rebase(item, old, new, root) for item in value]
    if isinstance(value, dict):
        return {rebase(key, old, new, root): rebase(item, old, new, root) for key, item in value.items()}
    return value


def session_identity(root: Path, workspace_id: str, logical_name: str) -> dict:
    """Allocate a UUID once, then resolve it through the durable session index."""
    index_path = _state(root) / "session-index.json"
    key = json.dumps([workspace_id, logical_name], separators=(",", ":"))
    index = _read(index_path)
    if key in index:
        return index[key]
    with identity_lock(root):
        index = _read(index_path)
        if key not in index:
            saved = _read(_session_metadata(root, workspace_id))
            existing = next((row.get("session_id") for row in saved.get("sessions", [])
                             if isinstance(row, dict) and row.get("name") == logical_name), None)
            index[key] = {"session_id": existing or str(uuid.uuid4()), "workspace_id": workspace_id,
                          "logical_name": logical_name}
            storage.write_json(index_path, index)
        return index[key]


def _session_metadata(root: Path, workspace_id: str) -> Path:
    from lab import paths
    if workspace_id == "__assistant__":
        return naming.workspace_metadata_file(root / ".lab")
    if workspace_id in {"__self__", "__cerebro__", "__logs__", "__vault__"}:
        if workspace_id == "__self__":
            root = paths.find_framework_root()
        return naming.pseudo_metadata_file(root, workspace_id.strip("_"))
    return naming.workspace_metadata_file(folder_for(root, workspace_id))


def session_owner(root: Path, tmux_name: str) -> tuple[str, str] | None:
    if not tmux_name.startswith("neurona-"):
        return None
    token = tmux_name.removeprefix("neurona-")
    if not re.fullmatch(r"[0-9a-f]{32}", token):
        return None
    for row in _read(_state(root) / "session-index.json").values():
        if str(row.get("session_id", "")).replace("-", "") == token:
            return row["workspace_id"], row["logical_name"]
    # A missing runtime index is recoverable from durable tab UUIDs.
    base = naming.workspaces_dir(root)
    candidates = [(scope, _session_metadata(root, scope)) for scope in
                  ("__self__", "__cerebro__", "__logs__", "__vault__", "__assistant__")]
    if base.is_dir():
        candidates.extend((folder.name, naming.workspace_metadata_file(folder))
                          for folder in base.iterdir() if folder.is_dir())
    for fallback_id, metadata in candidates:
        data = _read(metadata)
        for row in data.get("sessions", []):
            if isinstance(row, dict) and str(row.get("session_id", "")).replace("-", "") == token:
                return data.get("id", fallback_id), row["name"]
    return None


def forget_workspace(root: Path, workspace_id: str) -> None:
    """A deleted workspace's identifiers must not be reused by a new one."""
    with identity_lock(root):
        location_file = _state(root) / "workspace-locations.json"
        locations = _read(location_file)
        if workspace_id in locations:
            locations.pop(workspace_id)
            storage.write_json(location_file, locations)
        session_file = _state(root) / "session-index.json"
        sessions = _read(session_file)
        remaining = {key: row for key, row in sessions.items() if row.get("workspace_id") != workspace_id}
        if remaining != sessions:
            storage.write_json(session_file, remaining)


def rename_workspace(root: Path, workspace_id: str, name: str) -> dict:
    """Move a workspace and its path metadata, rolling back failed writes."""
    from lab import paths
    name = name.strip()
    if not name or len(name) > 80:
        raise ValueError("Workspace name must contain 1–80 characters")
    if workspace_id.startswith("__"):
        raise ValueError("Only real workspaces can be renamed")
    root = root.resolve()
    workspace_id = id_at(paths.workspace_dir(root, workspace_id))
    with identity_lock(root), workspace_operation(root, workspace_id):
        old = paths.workspace_dir(root, workspace_id)
        if old.is_symlink() or old.resolve() != old or not old.is_relative_to(root):
            raise ValueError("Cannot rename a linked workspace folder")
        metadata = naming.workspace_metadata_file(old)
        if not metadata.is_file():
            raise ValueError("Workspace not found")
        data = storage.read_json(metadata)
        workspace_id = data["id"]
        new = old.parent / slug(name)
        if new != old and new.exists():
            raise ValueError(f"A folder named {new.name!r} already exists")
        locations_path = _state(root) / "workspace-locations.json"
        locations = _read(locations_path)
        if new.name != workspace_id and paths.workspace_dir(root, new.name) not in (old, new):
            raise ValueError("That folder name is reserved by another workspace ID")
        snapshots: dict[Path, bytes | None] = {}
        writes: dict[Path, dict] = {}
        runtime_state = _state(root) / "runtimes" / workspace_id
        for file in [metadata, old / "tasks.json", old / "servers.json", old / "runtime.json",
                     paths.sessions_file(root), paths.ui_state_file(root), *runtime_state.rglob("*.json")]:
            if file.is_file():
                writes[file] = rebase(storage.read_json(file), old, new, root)
        writes[metadata]["name"] = name
        writes[metadata]["updated"] = date.today().isoformat()
        writes[metadata].setdefault("uuid", str(uuid.uuid4()))
        locations[workspace_id] = new.name
        writes[locations_path] = locations
        # A moved Git worktree keeps an absolute backlink in its gitdir.
        # Record those backlinks before the move so repair can run at the
        # new location even when the old pointer no longer resolves.
        repairs = []
        for parent, dirs, files in os.walk(old):
            dirs[:] = [d for d in dirs if d not in {".git", ".venv", "node_modules", "__pycache__"}]
            gitfile = Path(parent) / ".git"
            if ".git" in files:
                text = gitfile.read_text().strip()
                if text.startswith("gitdir: "):
                    gitdir = (gitfile.parent / text[8:]).resolve()
                    common_file = gitdir / "commondir"
                    if common_file.is_file():
                        common = (gitdir / common_file.read_text().strip()).resolve()
                        repairs.append((common, gitfile.parent.relative_to(old)))
        moved = False
        try:
            for file, value in writes.items():
                snapshots[file] = file.read_bytes() if file.exists() else None
                storage.write_json(file, value)
            if new != old:
                old.rename(new)
                moved = True
                for common, relative in repairs:
                    common = Path(rebase(str(common), old, new, root))
                    subprocess.run(["git", "--git-dir", str(common), "worktree", "repair", str(new / relative)],
                                   check=True, capture_output=True, text=True)
        except Exception:
            if moved:
                new.rename(old)
                for common, relative in repairs:
                    subprocess.run(["git", "--git-dir", str(common), "worktree", "repair", str(old / relative)],
                                   capture_output=True, text=True)
            for file, previous in snapshots.items():
                if previous is None:
                    file.unlink(missing_ok=True)
                else:
                    file.write_bytes(previous)
            raise
        return {**writes[metadata], "old_path": str(old), "path": str(new)}
