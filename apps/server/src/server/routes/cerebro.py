"""Cerebro tree + viewer endpoints.

"Cerebro" is the personal knowledge base that used to live at
``~/src/productivity/cerebro``; its content migrated into ``knowledge/`` in
this monorepo. This route serves the full structure of ``knowledge/`` as a
nested tree for the Obsidian-style browser. Markdown rendering goes through
``/api/markdown``.

Everything under ``knowledge/`` is included — wikis, logs, meetings,
roadmaps, skills, templates, AND the whole ``projects/`` subtree — so one
view covers both Cerebro content and per-project docs.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request


router = APIRouter()


# Dirs we don't want to crawl into, ever. Mostly ignored caches + vendor
# output + anything LLM-unfriendly (huge notebooks, compiled stuff).
_SKIP_DIRS = {
    ".git", ".venv", "venv", "__pycache__", "node_modules", ".mypy_cache",
    ".pytest_cache", "build", "dist", ".tox", ".eggs", ".gradle",
    ".ipynb_checkpoints",
}

# Cap the recursion in case someone symlinks wild trees under knowledge/.
_MAX_DEPTH = 8

# Extensions we consider "viewable" in the right-hand pane.
_MD_EXTS = {".md", ".markdown"}
_TEXT_EXTS = {".md", ".markdown", ".txt", ".json", ".yaml", ".yml", ".toml", ".py", ".sh"}


def _node(path: Path, rel: Path, include_hidden: bool) -> dict | None:
    name = path.name
    if not include_hidden and name.startswith(".") and name != ".":
        return None
    if path.is_dir():
        if name in _SKIP_DIRS:
            return None
        return {
            "name": name,
            "path": str(rel) if str(rel) != "." else "",
            "type": "dir",
            "children": [],
        }
    if path.is_file():
        suffix = path.suffix.lower()
        kind = "markdown" if suffix in _MD_EXTS else ("text" if suffix in _TEXT_EXTS else "file")
        try:
            size = path.stat().st_size
        except OSError:
            size = 0
        return {
            "name": name,
            "path": str(rel),
            "type": kind,
            "size": size,
        }
    return None


def _build(root: Path, rel_base: Path, include_hidden: bool, depth: int = 0) -> list[dict]:
    """Recursively build a sorted (dirs first, then files) tree under root."""
    if depth > _MAX_DEPTH:
        return []
    try:
        entries = sorted(root.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
    except (PermissionError, OSError):
        return []
    out: list[dict] = []
    for child in entries:
        node = _node(child, rel_base / child.name, include_hidden)
        if node is None:
            continue
        if node["type"] == "dir":
            node["children"] = _build(child, rel_base / child.name, include_hidden, depth + 1)
        out.append(node)
    return out


@router.get("/api/cerebro/tree")
async def cerebro_tree(request: Request, include_hidden: bool = False) -> list[dict]:
    """Return the whole ``knowledge/`` directory tree (the Cerebro view).

    Response is a list of top-level children under ``knowledge/`` (not the
    ``knowledge`` root itself, which would just be a wrapper). Dirs carry a
    ``children`` array; files carry a ``size`` + a ``type`` hint
    (``"markdown" | "text" | "file"``) the UI can use to decide whether to
    render inline or just list.
    """
    root: Path = request.app.state.index_cache.root
    kdir = root / "knowledge"
    if not kdir.is_dir():
        return []
    return _build(kdir, Path(""), include_hidden)
