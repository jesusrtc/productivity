"""Read scope-owned skill folders without scanning unrelated repository files."""
from __future__ import annotations

import os
from pathlib import Path

from core import fsguard

# Include current provider conventions, older Codex/Copilot locations, ordinary
# vault content, and Claude's backwards-compatible command skills.
SKILL_FOLDERS = (
    "skills", "content/skills", ".agents/skills", ".claude/skills",
    ".codex/skills", ".github/skills", ".copilot/skills", ".claude/commands",
)


def collect(root: Path) -> list[dict]:
    def entry(path: Path, ancestors: frozenset[Path], *, name: str | None = None) -> dict:
        fsguard.checkpoint()
        row = {"name": name or path.name, "path": path.relative_to(root).as_posix()}
        try:
            if path.is_symlink():
                row.update(is_symlink=True, symlink_target=os.readlink(path))
            directory = path.is_dir()
            row["type"] = "dir" if directory else "file"
            if not directory:
                if not path.is_file():
                    row["broken"] = True
                return row
            resolved = path.resolve()
            row["children"] = []
            if resolved in ancestors:
                row["cycle"] = True
                return row
            with os.scandir(path) as children:
                paths = [path / child.name for child in children]
            rows = [entry(child, ancestors | {resolved}) for child in paths]
            row["children"] = sorted(rows, key=lambda item: (item["type"] != "dir", item["name"].casefold(), item["name"]))
        except OSError:
            row.setdefault("type", "dir")
            row["unavailable"] = True
        return row

    folders = []
    for relative in SKILL_FOLDERS:
        fsguard.checkpoint()
        path = root / relative
        if path.is_dir():
            resolved_root = root.resolve()
            folders.append(entry(path, frozenset({resolved_root, *resolved_root.parents}), name=relative))
    return folders
