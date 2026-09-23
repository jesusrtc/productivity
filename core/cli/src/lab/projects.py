"""Shared project locations. Discovery never clones, moves, or creates folders."""
from __future__ import annotations

import os
from pathlib import Path

from lab import settings


def location(value: str, base: Path | None = None) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        if base is None:
            raise settings.SettingsError("Enter an absolute project path or a path starting with ~/")
        path = base / path
    return Path(os.path.abspath(path))


def worktree_folder(config: dict, project: Path) -> Path:
    for row in config["projectLocations"]:
        if location(row["path"]) == project and row.get("worktreeFolder"):
            return location(row["worktreeFolder"])
    return location(config["worktreesFolder"]) / project.name


def catalog(config: dict, checkpoint=lambda: None) -> dict:
    root = location(config["projectsFolder"])
    trees = location(config["worktreesFolder"])
    rows = {}
    warning = ""
    try:
        with os.scandir(root) as entries:
            for entry in entries:
                checkpoint()
                if entry.name.startswith(".") or Path(entry.path) == trees:
                    continue
                try:
                    if entry.is_dir():
                        rows[entry.path] = {"path": entry.path, "name": entry.name}
                except OSError:
                    continue
    except FileNotFoundError:
        warning = "Projects folder does not exist yet. Choose another folder or add a custom project."
    except NotADirectoryError:
        warning = "Projects folder is not a directory. Choose another folder."
    except PermissionError:
        warning = "Projects folder is not readable. Check its permissions or choose another folder."
    for row in config["projectLocations"]:
        checkpoint()
        path = location(row["path"])
        rows[str(path)] = {"path": str(path), "name": path.name}
    for row in rows.values():
        checkpoint()
        path = Path(row["path"])
        row.update(worktreeFolder=str(worktree_folder(config, path)), available=path.is_dir())
    return {"path": str(root), "worktreesFolder": str(trees), "home": str(Path.home()),
            "projects": sorted(rows.values(), key=lambda row: (row["name"].casefold(), row["path"])),
            "warning": warning}


def register(root: Path, rows: list[dict], base: Path | None = None) -> dict:
    """Validate the entire selection before atomically remembering custom locations."""
    normalized = []
    linked = set()
    for row in rows:
        raw = row.get("path", "").strip()
        if not raw or any(c in raw for c in "\x00\n\r"):
            raise settings.SettingsError("Every project needs a folder path")
        path = location(raw, base)
        if not path.is_dir():
            raise settings.SettingsError(f"Project folder not found: {path}")
        if path.is_symlink():
            linked.add(str(path))
        custom = row.get("worktreeFolder", "").strip()
        trees = str(location(custom, path)) if custom else ""
        normalized.append({"path": str(path), "worktreeFolder": trees})
    with settings._GLOBAL_WRITE_LOCK:
        config = settings.load(root)
        saved = {str(location(row["path"])): row for row in config["projectLocations"]}
        for row in normalized:
            path = Path(row['path'])
            # An empty workspace field inherits the catalog's project default;
            # adding that project must not erase its global worktree override.
            if not row['worktreeFolder'] and str(path) in saved:
                row = {**row, 'worktreeFolder': saved[str(path)].get('worktreeFolder', '')}
            # Keep defaults inherited. Only custom projects and explicit worktree
            # overrides need a catalog entry; scanning the root stays automatic.
            if path.parent != location(config["projectsFolder"]) or row['worktreeFolder'] or str(path) in saved or str(path) in linked:
                saved[str(path)] = row
        entries = list(saved.values())
        updated = settings.update_global(root, {"projectLocations": entries}) if entries != config['projectLocations'] else config
        return {"projects": normalized, "settings": updated}
