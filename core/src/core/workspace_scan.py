"""Shared, cycle-safe traversal for workspace files and refresh polling."""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import stat
from typing import Callable, Iterator

from core import fsguard


MAX_DEPTH = 16
SKIP_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv",
    ".mypy_cache", ".pytest_cache", "build", "dist", ".tox", ".eggs",
    "skills", "worktrees",
}


@dataclass
class Entry:
    path: Path
    stat: os.stat_result | None
    is_symlink: bool
    depth: int
    git_root: Path | None

    @property
    def is_dir(self) -> bool:
        return self.stat is not None and stat.S_ISDIR(self.stat.st_mode)

    @property
    def is_file(self) -> bool:
        return self.stat is not None and stat.S_ISREG(self.stat.st_mode)


def walk(root: Path, *, include_dotfiles: bool = False,
         git_root: Path | None = None,
         progress: Callable[[Path, str], None] | None = None) -> Iterator[Entry]:
    """Yield root, directories, files and broken links with one stat per entry.

    Linked folders remain browsable. Ancestor inode tracking stops cycles even
    when a link points at a Git root (which resets the per-checkout depth).
    Close each scandir iterator before yielding or descending: keeping parent
    iterators open would consume one descriptor per level per concurrent walk.
    """
    def step(path: Path, operation: str):
        fsguard.checkpoint()
        if progress:
            progress(path, operation)

    step(root, "stat")
    try:
        root_stat = root.stat()
    except (FileNotFoundError, NotADirectoryError):
        return
    if not stat.S_ISDIR(root_stat.st_mode):
        return

    def visit(entry: Entry, budget: int, ancestors: frozenset) -> Iterator[Entry]:
        step(entry.path, "visit")
        if not entry.is_dir or entry.path.name in SKIP_DIRS and entry.depth > 0:
            yield entry
            return
        identity = (entry.stat.st_dev, entry.stat.st_ino)
        if identity in ancestors or entry.depth > 64:
            yield entry
            return
        try:
            step(entry.path, "scandir")
            with os.scandir(entry.path) as iterator:
                children = []
                for child in iterator:
                    step(entry.path, "scandir")
                    children.append(child)
            step(entry.path, "sort")
            children.sort(key=lambda child: child.name)
        except (FileNotFoundError, NotADirectoryError, PermissionError):
            yield entry
            return
        if any(child.name == ".git" for child in children):
            entry.git_root = entry.path
            budget = 0
        yield entry
        if budget > MAX_DEPTH:
            return
        ancestors = ancestors | {identity}
        for child in children:
            if not include_dotfiles and child.name.startswith("."):
                continue
            step(Path(child.path), "stat")
            is_symlink = child.is_symlink()
            # Don't stat ordinary dependency directories we won't visit.
            if child.name in SKIP_DIRS and not is_symlink and child.is_dir(follow_symlinks=False):
                continue
            try:
                info = child.stat()
            except (FileNotFoundError, NotADirectoryError, PermissionError):
                if not is_symlink:
                    continue
                info = None
            yield from visit(Entry(Path(child.path), info, is_symlink,
                                   entry.depth + 1, entry.git_root), budget + 1, ancestors)

    yield from visit(Entry(root, root_stat, root.is_symlink(), 0, git_root), 0, frozenset())
