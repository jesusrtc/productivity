"""Read pre-vault Lab data at explicit compatibility boundaries.

New data uses vault/workspace names. Existing directory paths are stable so
running terminals, Git worktrees, and notebook kernels retain their identity.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

LEGACY_ROOT_ENV = "LAB_WORKSPACE"
LEGACY_REGISTRY = "workspaces.toml"
LEGACY_WORKSPACES_DIR = "projects"
LEGACY_WORKSPACE_FILE = "project.json"
LEGACY_VAULT_FILE = "workspace.json"


def workspaces_dir(root: Path) -> Path:
    """Use the canonical directory, or the existing pre-rename directory."""
    canonical = root / "workspaces"
    legacy = root / LEGACY_WORKSPACES_DIR
    return legacy if not canonical.exists() and legacy.is_dir() else canonical


def workspace_metadata_file(directory: Path) -> Path:
    canonical = directory / "workspace.json"
    for candidate in (canonical, directory / LEGACY_WORKSPACE_FILE,
                      directory / ".workspace.json", directory / ".project.json"):
        if candidate.is_file():
            return candidate
    return canonical


def vault_config_file(root: Path) -> Path:
    canonical = root / "vault.json"
    legacy = root / LEGACY_VAULT_FILE
    return legacy if not canonical.exists() and legacy.is_file() else canonical


def legacy_fields(value: Any) -> Any:
    """Translate a known legacy document's structural fields in one pass.

    Never rewrite user text, IDs, paths, command strings, or provider payloads.
    Only callers which have identified a legacy format may use this function.
    """
    names = {
        "workspaces": "vaults", "workspace": "vault",
        "workspace_id": "vault_id", "workspace_path": "vault_path",
        "workspace_name": "vault_name", "workspace_color": "vault_color",
        "projects": "workspaces", "project": "workspace",
        "project_id": "workspace_id", "project_path": "workspace_path",
        "project_name": "workspace_name", "parent_project": "parent_workspace",
    }
    if isinstance(value, list):
        return [legacy_fields(item) for item in value]
    if isinstance(value, dict):
        return {names.get(key, key): legacy_fields(item) for key, item in value.items()}
    return value


def runtime_metadata(data: dict) -> dict:
    """Migrate old terminal owner fields, preserving tmux names and cwd."""
    result = {}
    for name, row in data.items():
        if isinstance(row, dict) and "project_id" in row:
            row = legacy_fields(row)
            if row.get("workspace_id") == "__workspace__":
                row["workspace_id"] = "__vault__"
        result[name] = row
    return result


def workspace_document_file(directory: Path) -> Path:
    canonical = directory / "workspace.md"
    legacy = directory / "project.md"
    return legacy if not canonical.exists() and legacy.is_file() else canonical


def pseudo_metadata_file(root: Path, scope: str) -> Path:
    directory = root / "content"
    canonical = directory / f".{scope}-workspace.json"
    old_scope = "workspace" if scope == "vault" else scope
    legacy = directory / f".{old_scope}-project.json"
    return legacy if not canonical.exists() and legacy.is_file() else canonical
