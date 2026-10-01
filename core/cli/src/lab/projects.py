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


def sidebar_scopes(config: dict, checkpoint=lambda: None) -> dict:
    """Read project folders, their actual Git worktrees, and selectable parents.

    Only the picker calls this; ordinary sidebar refreshes keep their shallow
    reads. Git's NUL-delimited format preserves spaces/newlines in paths, and
    worktree registration finds custom destinations outside the default parent.
    """
    import subprocess

    data = catalog(config, checkpoint)
    scopes = {}

    def folder(path, name, kind='folder', **extra):
        path = str(path)
        scopes.setdefault(path, {'path': path, 'name': name, 'label': name,
                                 'kind': kind, 'available': Path(path).is_dir(), **extra})

    folder(data['path'], Path(data['path']).name, 'parent')
    folder(data['worktreesFolder'], Path(data['worktreesFolder']).name, 'parent')
    warnings = []
    for project in data['projects']:
        checkpoint()
        folder(project['path'], project['name'], worktreeFolder=project['worktreeFolder'])
        parent = Path(project['worktreeFolder'])
        if parent.is_dir():
            folder(parent, project['name'] + '/worktrees', 'parent')
        if not project['available'] or not (Path(project['path']) / '.git').exists():
            continue
        try:
            result = subprocess.run(
                ['git', '--no-optional-locks', '-C', project['path'],
                 'worktree', 'list', '--porcelain', '-z'],
                capture_output=True, timeout=3,
            )
        except (OSError, subprocess.TimeoutExpired):
            warnings.append(project['name'])
            continue
        if result.returncode:
            warnings.append(project['name'])
            continue
        records = []
        for record in result.stdout.decode('utf-8', errors='surrogateescape').split('\0\0'):
            fields = dict(field.partition(' ')[::2] for field in record.split('\0') if field)
            if fields.get('worktree'):
                records.append(fields)
        if not records:
            continue
        primary = records[0]['worktree']
        name = Path(primary).name
        for fields in records:
            checkpoint()
            path = fields['worktree']
            branch = fields.get('branch', '').removeprefix('refs/heads/')
            if path == primary:
                if path in scopes:
                    scopes[path]['branch'] = branch or 'detached'
                continue
            label = name + '/' + (branch or Path(path).name + ' (detached)')
            scopes[path] = {'path': path, 'name': Path(path).name, 'label': label,
                            'kind': 'worktree', 'projectPath': primary,
                            'branch': branch or 'detached', 'available': Path(path).is_dir(),
                            'worktreeFolder': ''}
            folder(Path(path).parent, name + '/worktrees', 'parent')
    data['scopes'] = sorted(scopes.values(), key=lambda row: (row['label'].casefold(), row['path']))
    if warnings:
        data['warning'] = ' '.join(filter(None, [data['warning'],
            'Could not read worktrees for: ' + ', '.join(warnings) + '. Retry to refresh.']))
    return data


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
