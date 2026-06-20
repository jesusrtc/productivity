"""Cerebro tree + viewer endpoints.

"Cerebro" is the personal knowledge base that used to live at
``~/src/productivity/cerebro``; its content migrated into ``content/`` in
this monorepo. This route serves the full structure of ``content/`` as a
nested tree for the Obsidian-style browser. Markdown rendering goes through
``/api/markdown``.

Everything under ``content/`` is included — wikis, logs, meetings,
roadmaps, skills, templates, AND the whole ``projects/`` subtree — so one
view covers both Cerebro content and per-project docs.
"""
from __future__ import annotations

import mimetypes
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse


router = APIRouter()


def _resolve_cerebro_path(root: Path, path: str) -> Path:
    """Validate + resolve a Cerebro path.

    The tree builder uses two namespaces depending on the subtree:

    * ``.claude/...`` — paths are monorepo-relative (the virtual top-level
      ``.claude/`` node is the shared `.claude/` at the monorepo root).
    * Everything else (e.g. ``code/spike_analysis.py``,
      ``wikis/foo.md``) — paths are relative to ``content/``.

    To accept both shapes from a single endpoint, try the monorepo-root
    resolution first (catches ``.claude/...``), then fall back to
    content-relative (catches the rest). Either resolution must land
    inside ``content/`` or ``.claude/``; absolute paths and traversal
    are rejected up-front.
    """
    if path.startswith("/") or ".." in Path(path).parts:
        raise HTTPException(status_code=400, detail="invalid path")
    content_root = (root / "content").resolve()
    shared_claude = (root / ".claude").resolve()
    shared_agents = (root / ".agents").resolve()
    shared_projects = (root / "projects").resolve()  # projects/ is a top-level sibling now
    # Canonical root instructions surfaced in every project's Meta section.
    # CLAUDE.md is a symlink to AGENTS.md, so both resolve to the same file.
    shared_files = {(root / "AGENTS.md").resolve(), (root / "CLAUDE.md").resolve()}
    candidates = (
        (root / path).resolve(),          # monorepo-relative — .claude/..., .agents/..., projects/... land here
        (content_root / path).resolve(),  # content-relative — code/..., wikis/..., etc.
    )
    for target in candidates:
        if target in shared_files:
            return target
        for allowed_root in (content_root, shared_claude, shared_agents, shared_projects):
            if target == allowed_root or allowed_root in target.parents:
                return target
    raise HTTPException(status_code=400, detail="path escapes content/, .claude/, .agents/ or projects/")


# Dirs we don't want to crawl into, ever. Mostly ignored caches + vendor
# output + anything LLM-unfriendly (huge notebooks, compiled stuff).
_SKIP_DIRS = {
    ".git", ".venv", "venv", "__pycache__", "node_modules", ".mypy_cache",
    ".pytest_cache", "build", "dist", ".tox", ".eggs", ".gradle",
    ".ipynb_checkpoints",
}

# Cap the recursion in case someone symlinks wild trees under content/.
_MAX_DEPTH = 8

# Extensions we consider "viewable" in the right-hand pane.
_MD_EXTS = {".md", ".markdown"}
_TEXT_EXTS = {".md", ".markdown", ".txt", ".json", ".yaml", ".yml", ".toml", ".py", ".sh", ".csv"}


def _symlink_fields(path: Path) -> dict:
    if not path.is_symlink():
        return {}
    try:
        target = os.readlink(path)
    except OSError:
        target = ""
    fields = {"is_symlink": True}
    if target:
        fields["symlink_target"] = target
    return fields


def _node(path: Path, rel: Path, include_hidden: bool) -> dict | None:
    name = path.name
    # `.claude/` carries the project's shared skills/agents/hooks. We
    # surface it by default so it's browseable from Cerebro; the only
    # subpath we hide is `.claude/logs/`, handled in `_build`.
    if not include_hidden and name.startswith(".") and name not in (".", ".claude"):
        return None
    if path.is_dir():
        if name in _SKIP_DIRS:
            return None
        if str(rel) == ".claude/logs":
            return None
        node = {
            "name": name,
            "path": str(rel) if str(rel) != "." else "",
            "type": "dir",
            "children": [],
        }
        node.update(_symlink_fields(path))
        return node
    if path.is_file():
        suffix = path.suffix.lower()
        kind = "markdown" if suffix in _MD_EXTS else ("text" if suffix in _TEXT_EXTS else "file")
        try:
            size = path.stat().st_size
        except OSError:
            size = 0
        node = {
            "name": name,
            "path": str(rel),
            "type": kind,
            "size": size,
        }
        node.update(_symlink_fields(path))
        return node
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


@router.get("/api/cerebro/file")
def cerebro_file(path: str, request: Request) -> dict:
    """Return raw text content of a non-markdown file under ``content/``.

    Used by the Cerebro viewer for ``.json`` / ``.csv`` / ``.html`` source
    (and other plain-text formats not rendered by ``/api/markdown``). Path
    is monorepo-relative (e.g. ``content/wikis/foo.csv``) and must resolve
    inside ``content/`` — OR the shared ``.claude/`` at the monorepo root
    (which Cerebro surfaces as a virtual top-level entry).
    """
    root: Path = request.app.state.index_cache.root
    target = _resolve_cerebro_path(root, path)
    if not target.is_file():
        raise HTTPException(status_code=404, detail="not found")
    suffix = target.suffix.lower()
    try:
        text = target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="binary file")
    kind = {".json": "json", ".csv": "csv", ".html": "html", ".htm": "html"}.get(suffix, "text")
    return {"content": text, "type": kind, "size": target.stat().st_size}


@router.get("/api/cerebro/asset")
def cerebro_asset(path: str, request: Request):
    """Serve a file from ``content/`` or shared ``.claude/`` with proper
    media-type — used as the iframe ``src`` for HTML rendering. Same path
    validation as ``/api/cerebro/file``.
    """
    root: Path = request.app.state.index_cache.root
    target = _resolve_cerebro_path(root, path)
    if not target.is_file():
        raise HTTPException(status_code=404, detail="not found")
    media_type, _ = mimetypes.guess_type(str(target))
    return FileResponse(target, media_type=media_type)


@router.get("/api/cerebro/tree")
def cerebro_tree(request: Request, include_hidden: bool = False) -> list[dict]:
    """Return the Cerebro tree — ``content/`` plus the monorepo-root ``.claude/``.

    Top-level entries are the children of ``content/`` (wikis, projects,
    logs, etc.) with one virtual addition: the monorepo's ``.claude/``
    (skills, agents, hooks, settings) is surfaced as a top-level ``.claude``
    node so users can browse shared tooling without leaving Cerebro. Paths
    for that subtree start with ``.claude/``; everything else is relative
    to ``content/``. ``.claude/logs/`` is hidden as before.
    """
    root: Path = request.app.state.index_cache.root
    kdir = root / "content"
    if not kdir.is_dir():
        return []
    nodes = _build(kdir, Path(""), include_hidden)
    # Prepend the shared `.claude/` if it exists at the monorepo root. The
    # tree builder reuses the same dotfile/skip rules, so .claude/logs/
    # stays hidden here just like inside content/.
    shared = root / ".claude"
    if shared.is_dir():
        shared_node = {
            "name": ".claude",
            "path": ".claude",
            "type": "dir",
            "children": _build(shared, Path(".claude"), include_hidden),
        }
        shared_node.update(_symlink_fields(shared))
        nodes.insert(0, shared_node)
    # Also surface the tool-neutral `.agents/` (config, memory, shared skills)
    # so it's browseable from every project's Meta section, like `.claude/`.
    shared_agents = root / ".agents"
    if shared_agents.is_dir():
        agents_node = {
            "name": ".agents",
            "path": ".agents",
            "type": "dir",
            "children": _build(shared_agents, Path(".agents"), include_hidden),
        }
        agents_node.update(_symlink_fields(shared_agents))
        nodes.insert(0, agents_node)
    # Surface the top-level `projects/` (popped out of content/) so projects
    # stay browseable in Cerebro, exactly as they were when nested under content/.
    projects = root / "projects"
    if projects.is_dir():
        projects_node = {
            "name": "projects",
            "path": "projects",
            "type": "dir",
            "children": _build(projects, Path("projects"), include_hidden),
        }
        projects_node.update(_symlink_fields(projects))
        nodes.insert(0, projects_node)
    return nodes
